from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Action:
    kind: str
    params: dict[str, Any]

    @classmethod
    def parse(cls, value: Any) -> Action:
        if not isinstance(value, dict) or set(value) != {"kind", "params"}:
            raise ValueError("action must contain only kind and params")
        if not isinstance(value["kind"], str) or not isinstance(value["params"], dict):
            raise ValueError("invalid action types")
        canonical(value)
        return cls(value["kind"], copy.deepcopy(value["params"]))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Outcome:
    accepted: bool
    reason: str
    event_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"accepted": self.accepted, "reason": self.reason, "event_ids": list(self.event_ids)}


class Rejected(ValueError):
    pass
