"""A real HTTP server over tests/fixtures/site, so the crawler is tested for
what it actually does — fetch over the network — rather than against a mock."""

from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path

import pytest

FIXTURE_SITE = Path(__file__).parent / "fixtures" / "site"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D102 - silence per-request logging
        pass


@pytest.fixture(scope="session")
def site_url() -> str:
    handler = functools.partial(_QuietHandler, directory=str(FIXTURE_SITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    yield f"http://{host}:{port}"
    server.shutdown()
    server.server_close()
