"""JSONL read/write helpers used for every artifact handed between teams."""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, TypeVar

T = TypeVar("T")


def _default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    raise TypeError(f"Cannot serialise {type(value)!r}")


def to_dict(record: Any) -> dict:
    return json.loads(json.dumps(dataclasses.asdict(record), default=_default))


def write_jsonl(path: str | Path, records: Iterable[Any]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            payload = record if isinstance(record, dict) else to_dict(record)
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            count += 1
    return count


def read_jsonl(path: str | Path, factory: Callable[[dict], T] | None = None) -> Iterator[T | dict]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No such artifact: {path}")
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} is not valid JSON") from exc
            yield factory(payload) if factory else payload


def write_json(path: str | Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = payload if isinstance(payload, dict) else to_dict(payload)
    path.write_text(
        json.dumps(body, indent=2, ensure_ascii=False, default=_default), encoding="utf-8"
    )


def read_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
