"""Try Agent Scout without touching the internet.

    python scripts/demo.py

Serves the six bundled fictional sample sites (tests/fixtures/sites/) on
127.0.0.1, runs `agent-scout run` on them and prints where the reports are.
Nothing is opened and nothing outside this machine is contacted.

The sites are invented for testing: three ordinary product sites, one
JavaScript shell, one site that answers 403 to everything and one whose
robots.txt is broken. The delay between requests is shortened to 0.5 s
because the server is local; a Crawl-delay in robots.txt is still honoured.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from agent_scout.cli import main as agent_scout_main  # noqa: E402
from fixture_server import FixtureSites  # noqa: E402

DEMO_PORT = 8641


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=Path("demo-output"), help="output directory (default: demo-output)")
    parser.add_argument("--delay", type=float, default=0.5, help="seconds between requests to one site (default 0.5)")
    parser.add_argument("--keep-serving", action="store_true",
                        help="keep the sample sites running afterwards so the source links in the report open")
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    with FixtureSites(base_port=DEMO_PORT) as sites:
        sites_file = args.out / "sites.yaml"
        sites_file.write_text(sites.sites_yaml(), encoding="utf-8", newline="\n")
        print("Serving 6 bundled fictional sample sites on 127.0.0.1 (invented for testing, not real products).")
        print(f"$ agent-scout run {sites_file} -o {args.out / 'reports'} --log-dir {args.out / 'logs'} --delay {args.delay:g}")
        print()
        code = agent_scout_main(["run", str(sites_file), "-o", str(args.out / "reports"),
                                 "--log-dir", str(args.out / "logs"), "--delay", str(args.delay)])
        if code != 0:
            return code
        print()
        print(f"Open {args.out / 'reports' / 'report.html'} in a browser.")
        if args.keep_serving:
            print("The sample sites stay up so the source links in the report work. Press Ctrl+C to stop.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print()
        else:
            print("The source links in the report point at the local sample server, which has now stopped;")
            print("run again with --keep-serving to follow them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
