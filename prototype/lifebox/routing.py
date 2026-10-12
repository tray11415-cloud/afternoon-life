from __future__ import annotations

import copy
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib import error, parse, request

from .model import Action, canonical, digest
from .policies import RoutinePolicy, _NoRedirect


class Task(StrEnum):
    ACTIVITY = "activity"
    DIALOGUE = "dialogue"
    CG_PROMPT = "cg_prompt"


class RouterError(RuntimeError):
    pass


@dataclass(frozen=True)
class Provider:
    backend: Any
    scope: str = "local"
    max_calls: int | None = None


class ModelRouter:
    """Select a backend by task/importance, with per-session call caps."""

    def __init__(self, providers: dict[str, Provider], routes: dict[tuple[str, str], tuple[str, ...]], cache_size: int = 128):
        if type(cache_size) is not int or not 1 <= cache_size <= 4096:
            raise ValueError("invalid cache size")
        for name, provider in providers.items():
            if not isinstance(name, str) or not name or provider.scope not in {"native", "local", "cloud", "fixture"}:
                raise ValueError("invalid provider")
            if provider.max_calls is not None and (type(provider.max_calls) is not int or provider.max_calls < 0):
                raise ValueError("invalid call cap")
        for (task, importance), names in routes.items():
            if task not in set(Task) or importance not in {"normal", "important"} or not names:
                raise ValueError("invalid route")
            if any(name not in providers for name in names):
                raise ValueError("unknown route provider")
            method = "decide" if task == Task.ACTIVITY else "generate"
            if any(not callable(getattr(providers[name].backend, method, None)) for name in names):
                raise ValueError("provider cannot handle route task")
        self.providers, self.routes = dict(providers), {key: tuple(value) for key, value in routes.items()}
        self._lock = threading.Lock()
        self._cache_size, self._cache = cache_size, OrderedDict()
        self._usage = {name: {"calls": 0, "cache_hits": 0, "failures": 0} for name in providers}

    def request(self, task: Task | str, context: dict, importance: str = "normal") -> Action | str:
        try:
            task = Task(task)
        except ValueError:
            raise RouterError("unsupported_task") from None
        if importance not in {"normal", "important"}:
            raise RouterError("invalid_importance")
        context = copy.deepcopy(context)
        candidates = self.routes.get((task.value, importance), ())
        for name in candidates:
            provider = self.providers[name]
            key = digest({"task": task.value, "provider": name, "context": context})
            with self._lock:
                if key in self._cache:
                    self._cache.move_to_end(key)
                    self._usage[name]["cache_hits"] += 1
                    return copy.deepcopy(self._cache[key])
                if provider.max_calls is not None and self._usage[name]["calls"] >= provider.max_calls:
                    continue
                self._usage[name]["calls"] += 1
            try:
                if task == Task.ACTIVITY:
                    raw = provider.backend.decide(copy.deepcopy(context))
                    result = Action.parse(raw.to_dict() if isinstance(raw, Action) else raw)
                else:
                    result = provider.backend.generate(task.value, copy.deepcopy(context))
                    if not isinstance(result, str) or not result.strip() or len(result) > 8000:
                        raise ValueError("invalid text output")
            except Exception:
                with self._lock:
                    self._usage[name]["failures"] += 1
                continue
            with self._lock:
                self._cache[key] = copy.deepcopy(result)
                self._cache.move_to_end(key)
                while len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
            return result
        raise RouterError("route_unavailable")

    def usage(self) -> dict:
        with self._lock:
            return {name: {"scope": self.providers[name].scope, "max_calls": self.providers[name].max_calls,
                           **copy.deepcopy(counts)} for name, counts in self._usage.items()}


class RoutedPolicy:
    def __init__(self, router: ModelRouter):
        self.router = router

    def decide(self, context: dict) -> Action:
        # Only concrete scheduling conflicts promote activity decisions.
        own = context["self"]["id"]
        pending = [inv for inv in context["invitations"] if inv["status"] == "pending" and inv["recipient"] == own]
        accepted = [inv for inv in context["invitations"] if inv["status"] in {"accepted", "active"}]
        conflict = any(left["start"] < right["end"] and right["start"] < left["end"] for left in pending for right in accepted)
        importance = "important" if conflict else "normal"
        action = self.router.request(Task.ACTIVITY, context, importance)
        if action.kind == "say" and set(action.params) == {"text", "target"}:
            target = action.params["target"]
            nearby_ids = {person["id"] for person in context["nearby"]}
            if target is None or isinstance(target, str) and target in nearby_ids:
                dialogue = {"actor_view": context, "target": target, "speech_intent": action.params["text"]}
                text = self.router.request(Task.DIALOGUE, dialogue, importance)
                return Action("say", {"text": text, "target": target})
        return action


class FixtureBackend(RoutinePolicy):
    """Explicit offline fixture; not a real local or cloud model."""

    def generate(self, task: str, context: dict) -> str:
        if task == Task.DIALOGUE:
            return "這是一句測試回覆。"
        if task == Task.CG_PROMPT:
            return "an ordinary shared living space, soft daylight, everyday illustration"
        raise ValueError("unsupported fixture task")


def fixture_router() -> ModelRouter:
    providers = {"native": Provider(RoutinePolicy(), "native"),
                 "dialogue_fixture": Provider(FixtureBackend(), "fixture", 1000),
                 "important_fixture": Provider(FixtureBackend(), "fixture", 20),
                 "cg_fixture": Provider(FixtureBackend(), "fixture", 100)}
    routes = {(Task.ACTIVITY, "normal"): ("native",),
              (Task.ACTIVITY, "important"): ("important_fixture", "native"),
              (Task.DIALOGUE, "normal"): ("dialogue_fixture",),
              (Task.DIALOGUE, "important"): ("important_fixture", "dialogue_fixture"),
              (Task.CG_PROMPT, "normal"): ("cg_fixture",),
              (Task.CG_PROMPT, "important"): ("important_fixture", "cg_fixture")}
    return ModelRouter(providers, routes)


class RemoteTextBackend:
    """Provider-neutral text gateway; separate endpoint/model from activity."""

    def __init__(self, endpoint: str, api_key: str = "", timeout: float = 10):
        url = parse.urlsplit(endpoint)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if url.scheme not in {"http", "https"} or (url.scheme == "http" and not local):
            raise ValueError("use HTTPS or localhost HTTP")
        if not url.hostname or url.username or url.password or url.fragment or not 0 < timeout <= 60:
            raise ValueError("invalid gateway configuration")
        self.endpoint, self.api_key, self.timeout = endpoint, api_key, timeout
        self._opener = request.build_opener(_NoRedirect)

    def generate(self, task: str, context: dict) -> str:
        if task not in {Task.DIALOGUE, Task.CG_PROMPT}:
            raise RouterError("unsupported_text_task")
        actor_view = context.get("actor_view", {})
        actor_id = actor_view.get("self", {}).get("id") if isinstance(actor_view, dict) else None
        body = canonical({"schema_version": 1, "task": task, "actor_id": actor_id, "context": context,
                          "response_contract": {"text": "nonempty string, <=8000 characters"}}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        try:
            with self._opener.open(request.Request(self.endpoint, body, headers, method="POST"), timeout=self.timeout) as response:
                data = response.read(65537)
            if len(data) > 65536:
                raise ValueError("response too large")
            result = json.loads(data.decode("utf-8"))
            if not isinstance(result, dict) or set(result) != {"text"} or not isinstance(result["text"], str) or not 0 < len(result["text"].strip()) <= 8000:
                raise ValueError("invalid response")
            return result["text"]
        except (error.URLError, TimeoutError, OSError, ValueError, TypeError, UnicodeError):
            raise RouterError("text_gateway_failed") from None
