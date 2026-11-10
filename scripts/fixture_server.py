"""Local HTTP servers for the bundled fictional sample sites.

Each directory under tests/fixtures/sites/ is one invented product website
(every name ends in "(fictional)" and every page carries a banner saying so).
Each site is served on its own port of 127.0.0.1 so that it has its own
robots.txt and its own request pacing, exactly like a separate host.

Site behaviour is declared in the site's ``_site.json``:

    name                   display name
    content_encoding       "gzip" or "br": compress responses when the client
                           advertises that encoding
    charset                serve HTML transcoded to this charset (source files
                           are UTF-8) and declare it in Content-Type
    charset_header_except  paths whose Content-Type omits the charset, so only
                           the <meta charset> declares it
    status_all             answer every request with this status (403 site)
    robots_status          answer /robots.txt with this status
    redirects              {"/from": "/to"} answered with 302

Used by the test suite (tests/conftest.py), scripts/demo.py and
scripts/make_demo_video.py. Nothing here talks to the internet.
"""

from __future__ import annotations

import gzip
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import brotli

SITES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sites"
GROUND_TRUTH_DIR = SITES_DIR.parent / "ground-truth"

CONTENT_TYPES = {
    ".html": "text/html",
    ".txt": "text/plain",
    ".js": "text/javascript",
    ".json": "application/json",
    ".svg": "image/svg+xml",
}


@dataclass
class RequestRecord:
    path: str
    headers: dict[str, str]
    status: int


@dataclass
class RunningSite:
    slug: str
    name: str
    root: Path
    behaviour: dict
    server: ThreadingHTTPServer
    thread: threading.Thread
    requests: list[RequestRecord] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/"

    def paths(self) -> list[str]:
        return [record.path for record in self.requests]


def _resolve(root: Path, path: str) -> Path | None:
    """Map a URL path to a file under root: /x -> x.html, x/index.html or x."""
    clean = path.strip("/")
    if ".." in clean.split("/") or clean.startswith("_"):
        return None
    candidates = [root / "index.html"] if not clean else [
        root / clean, root / f"{clean}.html", root / clean / "index.html"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _make_handler(site: RunningSite):
    behaviour = site.behaviour

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep test output quiet
            pass

        def _send(self, status: int, body: bytes, content_type: str, extra: dict[str, str] | None = None):
            headers = dict(extra or {})
            encoding = behaviour.get("content_encoding")
            accepted = [part.split(";")[0].strip() for part in self.headers.get("Accept-Encoding", "").split(",")]
            if encoding and encoding in accepted and body:
                body = gzip.compress(body) if encoding == "gzip" else brotli.compress(body)
                headers["Content-Encoding"] = encoding
                headers["Vary"] = "Accept-Encoding"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            site.requests.append(RequestRecord(self.path, dict(self.headers.items()), status))

        def do_GET(self):
            path = urlsplit(self.path).path
            if "status_all" in behaviour:
                denied = (site.root / "denied.html").read_bytes()
                return self._send(behaviour["status_all"], denied, "text/html; charset=utf-8")
            if path == "/robots.txt" and "robots_status" in behaviour:
                return self._send(behaviour["robots_status"], b"temporarily broken\n", "text/plain")
            if path in behaviour.get("redirects", {}):
                return self._send(302, b"", "text/html", {"Location": behaviour["redirects"][path]})
            target = _resolve(site.root, path)
            if target is None:
                return self._send(404, b"<!doctype html><title>Not found</title><p>Not found.</p>",
                                  "text/html; charset=utf-8")
            body = target.read_bytes()
            content_type = CONTENT_TYPES.get(target.suffix, "application/octet-stream")
            if target.suffix == ".html":
                charset = behaviour.get("charset", "utf-8")
                if charset != "utf-8":
                    body = body.decode("utf-8").encode(charset)
                if path not in behaviour.get("charset_header_except", []):
                    content_type += f"; charset={charset}"
            elif target.suffix in (".txt", ".js"):
                content_type += "; charset=utf-8"
            return self._send(200, body, content_type)

        do_HEAD = do_GET

    return Handler


def start_site(root: Path, port: int = 0) -> RunningSite:
    behaviour = json.loads((root / "_site.json").read_text(encoding="utf-8"))
    server = ThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
    site = RunningSite(slug=root.name, name=behaviour["name"], root=root, behaviour=behaviour,
                       server=server, thread=threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02},
                                               daemon=True))
    server.RequestHandlerClass = _make_handler(site)
    site.thread.start()
    return site


class FixtureSites:
    """All bundled sample sites, running. Use as a context manager."""

    def __init__(self, base_port: int | None = None):
        self.sites: list[RunningSite] = []
        roots = sorted(path for path in SITES_DIR.iterdir() if (path / "_site.json").is_file())
        for index, root in enumerate(roots):
            port = 0 if base_port is None else base_port + index
            try:
                self.sites.append(start_site(root, port))
            except OSError:
                self.sites.append(start_site(root, 0))   # port taken: let the OS choose

    def __getitem__(self, slug: str) -> RunningSite:
        for site in self.sites:
            if site.slug == slug:
                return site
        raise KeyError(slug)

    def sites_yaml(self) -> str:
        lines = ["# Bundled fictional sample sites, served locally by scripts/fixture_server.py"]
        for site in self.sites:
            lines.append(f"- slug: {site.slug}")
            lines.append(f"  name: \"{site.name}\"")
            lines.append(f"  url: {site.url}")
        return "\n".join(lines) + "\n"

    def stop(self) -> None:
        for site in self.sites:
            site.server.shutdown()
            site.server.server_close()
            site.thread.join(timeout=5)

    def __enter__(self) -> "FixtureSites":
        return self

    def __exit__(self, *exc) -> None:
        self.stop()


if __name__ == "__main__":
    import time

    with FixtureSites(base_port=8641) as running:
        print(running.sites_yaml())
        print("Serving the fictional sample sites. Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
