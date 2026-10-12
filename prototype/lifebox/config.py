from __future__ import annotations

import json
import os
from pathlib import Path

from .policies import RemotePolicy, RoutinePolicy
from .routing import ModelRouter, Provider, RemoteTextBackend


def load_router(path: str | Path) -> ModelRouter:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict) or set(config) != {"schema_version", "providers", "routes"} or config["schema_version"] != 1:
        raise ValueError("invalid model routing config")
    if not isinstance(config["providers"], dict) or not isinstance(config["routes"], list):
        raise ValueError("invalid providers or routes")
    providers = {}
    for name, spec in config["providers"].items():
        if not isinstance(spec, dict) or set(spec) - {"kind", "scope", "endpoint_env", "key_env", "max_calls"} or not {"kind", "scope"} <= set(spec):
            raise ValueError("invalid provider config")
        if spec["kind"] == "rules":
            backend = RoutinePolicy()
        elif spec["kind"] in {"action_gateway", "text_gateway"}:
            env_name = spec.get("endpoint_env")
            key_name = spec.get("key_env")
            if not isinstance(env_name, str) or not env_name or key_name is not None and not isinstance(key_name, str):
                raise ValueError("invalid endpoint/key environment variable name")
            endpoint = os.environ.get(env_name, "")
            if not endpoint:
                raise ValueError(f"missing endpoint environment variable: {env_name}")
            key = os.environ.get(key_name, "") if key_name else ""
            backend = RemotePolicy(endpoint, key) if spec["kind"] == "action_gateway" else RemoteTextBackend(endpoint, key)
        else:
            raise ValueError("unknown provider kind")
        providers[name] = Provider(backend, spec["scope"], spec.get("max_calls"))
    routes = {}
    for route in config["routes"]:
        if not isinstance(route, dict) or set(route) != {"task", "importance", "providers"} or not isinstance(route["providers"], list):
            raise ValueError("invalid route config")
        key = (route["task"], route["importance"])
        if key in routes:
            raise ValueError("duplicate route")
        routes[key] = tuple(route["providers"])
    required = {(task, importance) for task in ("activity", "dialogue", "cg_prompt") for importance in ("normal", "important")}
    if set(routes) != required:
        raise ValueError("all three tasks need normal and important routes")
    return ModelRouter(providers, routes)
