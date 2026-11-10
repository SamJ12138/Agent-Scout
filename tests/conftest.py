"""Shared fixtures. Nothing in the suite touches the network: every HTTP
request goes to a server started here on 127.0.0.1."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agent_scout import obs
from agent_scout.config import Config
from fixture_server import FixtureSites


class FakeTime:
    """A clock that only moves when something sleeps on it."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 6))
        self.now += seconds


@pytest.fixture
def fake_time():
    return FakeTime()


@pytest.fixture(scope="session")
def fixture_sites():
    with FixtureSites() as sites:
        yield sites


@pytest.fixture
def events(tmp_path):
    """Install a run log for the test; call the fixture to read the events so far."""
    path = tmp_path / "events.jsonl"
    log = obs.EventLog(path, run_id="test")
    obs.set_current(log)

    def read():
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    read.log = log
    read.path = path
    yield read
    obs.set_current(None)
    log.close()


class ScriptedServer:
    """A server whose responses are scripted per path.

    ``route(path, status, headers, body)`` may be called several times for one
    path: responses are served in order and the last one repeats.
    """

    def __init__(self):
        self.routes: dict[str, list[tuple[int, dict, bytes, float]]] = {}
        self.hits: list[tuple[str, dict]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                import time
                outer.hits.append((self.path, dict(self.headers.items())))
                queue = outer.routes.get(self.path)
                if not queue:
                    status, headers, body, delay = 404, {"Content-Type": "text/html"}, b"<p>missing</p>", 0.0
                else:
                    status, headers, body, delay = queue[0] if len(queue) == 1 else queue.pop(0)
                headers = dict(headers)
                stall = float(headers.pop("X-Test-Stall-Body", 0))        # send half the body, then wait
                declared = headers.pop("X-Test-Declared-Length", None)    # lie about the length, then close
                lower = headers.pop("X-Test-Lowercase-Names", None)       # write every header name in lower case
                if lower:
                    headers = {name.lower(): value for name, value in headers.items()}
                if delay:
                    time.sleep(delay)
                try:
                    if lower:
                        self.send_response_only(status)       # no Server / Date headers in mixed case
                    else:
                        self.send_response(status)
                    for name, value in headers.items():
                        self.send_header(name, value)
                    self.send_header("content-length" if lower else "Content-Length", declared or str(len(body)))
                    self.end_headers()
                    if stall:
                        self.wfile.write(body[:len(body) // 2])
                        self.wfile.flush()
                        time.sleep(stall)
                        self.wfile.write(body[len(body) // 2:])
                    else:
                        self.wfile.write(body)
                    if declared:
                        self.close_connection = True
                except OSError:
                    pass  # client gave up (timeout tests)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def route(self, path, status=200, headers=None, body=b"", delay=0.0):
        merged = {"Content-Type": "text/html; charset=utf-8"}
        merged.update(headers or {})
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.routes.setdefault(path, []).append((status, merged, body, delay))
        return self

    def paths(self):
        return [path for path, _ in self.hits]

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def scripted():
    server = ScriptedServer()
    yield server
    server.stop()


@pytest.fixture
def make_fetcher(fake_time):
    from agent_scout.fetch import Fetcher

    def build(**settings):
        settings.setdefault("delay_seconds", 0.0)
        settings.setdefault("timeout_seconds", 5.0)
        return Fetcher(Config(**settings), sleep=fake_time.sleep, clock=fake_time.clock)

    return build


def html_page(body: str, title: str = "Test page", head: str = "") -> str:
    return f"<!doctype html><html><head><title>{title}</title>{head}</head><body>{body}</body></html>"
