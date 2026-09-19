"""Stage 5: download the in-scope documents. No browser. Spec §6.11.

Files are stored FLAT in `_files/`, not inside section folders. The same PDF is
linked from many pages — the staff list appears in the footer of every one — so
storing per section produces several copies with no canonical one. The
page-to-file relationship lives in each page's .json and in index.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import config
from .api import Blocked, Client, ImageRefused
from .paths import is_image_url, page_id, safe_name

log = logging.getLogger(__name__)


def run(client: Client, out: Path | None = None, *,
        force: bool = False, limit: int | None = None) -> dict:
    out = out or config.OUT
    files_dir = out / "_files"
    files_dir.mkdir(parents=True, exist_ok=True)
    meta_dir = out / "_meta"

    records_path = meta_dir / "found_files.json"
    if not records_path.exists():
        log.error("no found_files.json; run --stage content first")
        return {"downloaded": 0, "skipped": 0, "errors": []}

    records = json.loads(records_path.read_text(encoding="utf-8"))
    index_path = files_dir / "index.json"
    index = {}
    if index_path.exists():
        index = {r["url"]: r for r in json.loads(index_path.read_text(encoding="utf-8"))}

    downloaded = skipped = images_skipped = 0
    errors: list[dict] = []
    attempted = 0

    for record in records:
        url = record["url"]

        # Second line of defence. An image reaching this stage means a filter
        # upstream has a hole, so it is a WARNING rather than a silent skip.
        # Spec §6.11.
        if is_image_url(url):
            log.warning("IMAGE reached the file stage, which is a bug upstream: %s", url)
            images_skipped += 1
            continue

        # `download: False` marks a file we recorded but deliberately do not
        # fetch — the 693 out-of-scope notices. Keeping the metadata is free;
        # fetching 693 PDFs is not. Part 2 §3.4.
        if record.get("download") is False:
            skipped += 1
            continue

        if limit is not None and attempted >= limit:
            break
        attempted += 1

        name = safe_name(url.rsplit("/", 1)[-1].split("?")[0] or "file")
        dest = files_dir / f"{page_id(url)[:8]}__{name}"

        if dest.exists() and not force:
            skipped += 1
            index.setdefault(url, {**record, "local": dest.name,
                                   "bytes": dest.stat().st_size})
            continue

        try:
            response = client.get(url, stream=True, max_bytes=config.MAX_FILE_BYTES)
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")

            # Write to .part and rename, so an interrupted download is never
            # mistaken for a complete one. Spec §6.11, §7.3.
            tmp = dest.with_suffix(dest.suffix + ".part")
            tmp.write_bytes(response.content)
            tmp.replace(dest)

            index[url] = {
                **record,
                "local": f"_files/{dest.name}",
                "bytes": len(response.content),
                "content_type": response.headers.get("Content-Type", ""),
            }
            downloaded += 1
            log.info("file %8d B  %s", len(response.content), dest.name)

        except ImageRefused:
            images_skipped += 1
            log.warning("image refused at fetch: %s", url)
        except Blocked:
            errors.append({"url": url, "stage": "files", "error": "RobotsDisallowed"})
            log.warning("robots disallows %s", url)
        except Exception as exc:                     # noqa: BLE001
            errors.append({"url": url, "stage": "files",
                           "error": type(exc).__name__, "message": str(exc)})
            log.warning("file FAILED %s: %s", url, exc)

    index_path.write_text(
        json.dumps(list(index.values()), ensure_ascii=False, indent=2),
        encoding="utf-8")

    log.info("files: %d downloaded, %d skipped, %d images refused, %d errors",
             downloaded, skipped, images_skipped, len(errors))
    return {"downloaded": downloaded, "skipped": skipped,
            "images_skipped": images_skipped, "errors": errors,
            "bytes": sum(r.get("bytes", 0) for r in index.values())}
