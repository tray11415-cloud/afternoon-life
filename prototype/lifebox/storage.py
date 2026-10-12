from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .engine import Engine
from .model import canonical, digest

MAX_SAVE_BYTES = 32 * 1024 * 1024


def save(engine: Engine, path: str | Path) -> Path:
    """Write complete journal to a sibling temporary file, then atomically replace."""
    destination = Path(path)
    payload = engine.journal()
    envelope = {"payload": payload, "checksum": digest(payload)}
    data = canonical(envelope).encode("utf-8")
    if len(data) > MAX_SAVE_BYTES:
        raise ValueError("save exceeds prototype size limit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


def load(path: str | Path) -> Engine:
    source = Path(path)
    with source.open("rb") as stream:
        data = stream.read(MAX_SAVE_BYTES + 1)
    if len(data) > MAX_SAVE_BYTES:
        raise ValueError("save exceeds prototype size limit")
    try:
        envelope = json.loads(data.decode("utf-8"))
        if not isinstance(envelope, dict) or set(envelope) != {"payload", "checksum"}:
            raise ValueError("invalid save envelope")
        if envelope["checksum"] != digest(envelope["payload"]):
            raise ValueError("save checksum mismatch")
        return Engine.replay(envelope["payload"])
    except (UnicodeError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        raise ValueError("invalid save data") from exc
