"""One polite HTTP client, shared by every stage that touches the network.

Stages 1, 2, 5 and 6 all make requests. Four copies of the rate limiting would
be four chances to get it wrong, and getting it wrong here means being blocked
from a third-party university server with no quick way back. Spec §7.4.

Nothing in this module knows about CUET's content. It knows about manners.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from . import config
from .paths import canonical, is_image_url

log = logging.getLogger(__name__)


class Blocked(Exception):
    """robots.txt disallows this URL. An ordinary outcome, not an error."""


class ImageRefused(Exception):
    """An image URL reached the fetcher.

    Raised rather than quietly skipped: images are excluded upstream, so one
    arriving here means a filter has a hole in it. Spec §6.11 asks for a WARNING
    rather than a silent skip for exactly this reason.
    """


@dataclass
class Response:
    url: str
    status: int
    content: bytes
    headers: dict = field(default_factory=dict)
    elapsed_ms: int = 0

    @property
    def text(self) -> str:
        """Decoded body, preferring the document's own declared charset.

        The HTTP header and the `<meta charset>` are two separate declarations
        and can disagree; the document's own is the more reliable. Spec §4.12.

        `content` stays available as bytes regardless — a mis-decode here is
        recoverable, a mis-decoded *save* is not.
        """
        return self.content.decode("utf-8", errors="replace")


class Client:
    """One instance per run. Tracks per-host timing and robots rules."""

    def __init__(self, *, delay: float | None = None, user_agent: str | None = None):
        self.delay = config.DELAY if delay is None else delay
        self.user_agent = user_agent or config.USER_AGENT
        self._last: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self._lock = threading.Lock()
        self._session = requests.Session()
        self._session.headers["User-Agent"] = self.user_agent
        self.request_count = 0

    # -- politeness --------------------------------------------------------

    def allowed(self, url: str) -> bool:
        """Does robots.txt permit this URL?

        Fetched once per origin and cached — fetching robots.txt before every
        request is itself abusive.

        VERIFIED 2026-09-08: cuet.ac.bd/robots.txt returns 404, so there is no
        robots.txt and everything is allowed. `RobotFileParser.read()` already
        handles a 4xx as allow-all, so this needs no special case — but note it
        must never be handed the 404 *body*, which is 51 KB of styled HTML.
        Spec §4.5, §7.4.
        """
        if not config.OBEY_ROBOTS:
            return True
        parts = urlsplit(canonical(url))
        origin = f"{parts.scheme}://{parts.netloc}"

        with self._lock:
            cached = origin in self._robots
            parser = self._robots.get(origin)

        if not cached:
            # Fetched OUTSIDE the lock, deliberately. _load_robots rate-limits
            # itself, and _wait_turn takes this same lock — holding it here
            # deadlocks. It would also serialise every worker behind one
            # network round-trip once concurrency is switched on.
            parser = self._load_robots(origin)
            with self._lock:
                self._robots.setdefault(origin, parser)
                parser = self._robots[origin]

        if parser is None:            # unreachable: allow, but it was logged
            return True
        return parser.can_fetch(self.user_agent, url)

    def _load_robots(self, origin: str) -> RobotFileParser | None:
        """Fetch and parse one origin's robots.txt.

        Fetched with our own session rather than `RobotFileParser.read()`, for
        two reasons that both bit us on this site:

        * `read()` has no timeout and will hang the whole run on a slow host.
        * `read()` feeds the response body to the parser based on status alone.
          cuet.ac.bd returns **404 with 51 KB of styled HTML** (spec §4.5), and
          any body that reaches the parser is interpreted as rules. Checking the
          status ourselves and only parsing a 2xx makes that impossible.
        """
        parser = RobotFileParser()
        parser.set_url(f"{origin}/robots.txt")
        url = f"{origin}/robots.txt"
        try:
            self._wait_turn(urlsplit(origin).netloc)
            response = self._session.get(url, timeout=config.HTTP_TIMEOUT)
            self.request_count += 1
        except requests.RequestException as exc:
            log.warning("robots.txt unreachable for %s (%s); proceeding as allow-all",
                        origin, exc)
            return None

        if response.status_code in (401, 403):
            # The standard: authorisation required means the whole site is
            # disallowed. Rare, but it is not the same as "missing".
            parser.disallow_all = True
            log.warning("robots.txt for %s returned %d; treating as disallow-all",
                        origin, response.status_code)
            return parser

        if response.status_code >= 400:
            # VERIFIED for cuet.ac.bd: 404. Allow-all per the standard, logged
            # because it is a fact about the site worth seeing in every run.
            parser.allow_all = True
            log.info("no robots.txt for %s (HTTP %d) - allow-all per the standard. "
                     "That is not permission: DELAY and USER_AGENT are the only "
                     "restraint left (spec §7.4).", origin, response.status_code)
            return parser

        parser.parse(response.text.splitlines())
        log.info("robots.txt loaded for %s (%d bytes)", origin, len(response.content))
        return parser

    def _wait_turn(self, host: str) -> None:
        """Block until `delay` has passed since the last request to this host.

        Per host, not global: crawling app.cuet.ac.bd must not consume the
        cuet.ac.bd budget. Spec §7.4.

        Uses a monotonic clock because a wall clock can jump backwards and would
        then hand out an unbounded burst.
        """
        with self._lock:
            now = time.monotonic()
            previous = self._last.get(host)
            if previous is not None:
                remaining = self.delay - (now - previous)
                if remaining > 0:
                    time.sleep(remaining)
                    now = time.monotonic()
            self._last[host] = now

    # -- fetching ----------------------------------------------------------

    def get(self, url: str, *, stream: bool = False,
            max_bytes: int | None = None, headers: dict | None = None) -> Response:
        """GET with rate limiting, robots and retries.

        Raises `Blocked` if robots says no and `ImageRefused` for an image URL —
        both are outcomes a caller should handle, not crashes.
        """
        if is_image_url(url):
            raise ImageRefused(url)

        if not self.allowed(url):
            raise Blocked(url)

        host = urlsplit(canonical(url)).netloc
        cap = config.MAX_FILE_BYTES if max_bytes is None else max_bytes
        last_error: Exception | None = None

        for attempt in range(1, config.MAX_RETRIES + 1):
            self._wait_turn(host)
            started = time.monotonic()
            try:
                response = self._session.get(
                    url, timeout=config.HTTP_TIMEOUT, stream=stream,
                    headers=headers or {},
                )
                self.request_count += 1
            except requests.RequestException as exc:
                last_error = exc
                self._backoff(attempt, None, url, str(exc))
                continue

            # 404 and 403 are final. Retrying them wastes the host's time and
            # ours, and a 404 will still be a 404. Spec §7.4.
            if response.status_code in config.RETRY_STATUSES:
                retry_after = response.headers.get("Retry-After")
                last_error = RuntimeError(f"HTTP {response.status_code}")
                response.close()
                self._backoff(attempt, retry_after, url,
                              f"HTTP {response.status_code}")
                continue

            content = self._read_capped(response, cap, url)
            return Response(
                url=url,
                status=response.status_code,
                content=content,
                headers=dict(response.headers),
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )

        raise RuntimeError(f"giving up on {url} after {config.MAX_RETRIES} attempts: {last_error}")

    def _read_capped(self, response: requests.Response, cap: int, url: str) -> bytes:
        """Read a body, aborting mid-stream if it exceeds the cap.

        Checking Content-Length is not enough — it is advisory and may be absent
        or wrong. Streaming and counting is what actually stops a surprise 2 GB
        file from ending the run on an 8 GB laptop. Spec §6.11, §7.4.
        """
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=65_536):
            if not chunk:
                continue
            total += len(chunk)
            if total > cap:
                response.close()
                raise RuntimeError(f"{url} exceeded {cap} bytes; aborted mid-stream")
            chunks.append(chunk)
        response.close()
        return b"".join(chunks)

    def _backoff(self, attempt: int, retry_after: str | None,
                 url: str, reason: str) -> None:
        """Exponential backoff, honouring Retry-After, capped. Spec §7.4."""
        if retry_after:
            try:
                wait = min(float(retry_after), config.BACKOFF_CAP)
            except ValueError:                       # an HTTP-date, not seconds
                wait = min(2 ** attempt, config.BACKOFF_CAP)
        else:
            # Jitter so that concurrent workers hitting the same limit do not
            # all retry on the same tick and reproduce the burst that caused it.
            wait = min(2 ** attempt + random.uniform(0, 1), config.BACKOFF_CAP)
        log.warning("%s on %s (attempt %d/%d); backing off %.1fs",
                    reason, url, attempt, config.MAX_RETRIES, wait)
        time.sleep(wait)

    # -- convenience -------------------------------------------------------

    def get_json(self, url: str):
        import json
        response = self.get(url)
        if response.status != 200:
            raise RuntimeError(f"{url} returned HTTP {response.status}")
        return json.loads(response.content.decode("utf-8"))

    def close(self) -> None:
        self._session.close()
