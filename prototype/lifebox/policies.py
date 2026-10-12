from __future__ import annotations

import copy
import json
from typing import Protocol
from urllib import error, parse, request

from .model import Action, canonical


class Policy(Protocol):
    def decide(self, context: dict) -> Action | dict: ...


class RoutinePolicy:
    """Deterministic wiring fixture. This is not a language model or personality."""

    def decide(self, context: dict) -> Action:
        actor, tick = context["self"], context["tick"]
        for invitation in context["invitations"]:
            if invitation["recipient"] == actor["id"] and invitation["status"] == "pending":
                return Action("respond", {"invitation_id": invitation["id"], "accept": True})
        upcoming = sorted((inv for inv in context["invitations"] if inv["status"] == "accepted"), key=lambda inv: inv["start"])
        if upcoming:
            invitation = upcoming[0]
            if actor["location"] != invitation["location"]:
                # All fixture paths go through shared. No access to a hidden global map.
                destination = invitation["location"] if invitation["location"] in context["paths"] else "shared"
                if destination in context["paths"]:
                    return Action("move", {"location": destination})
            if invitation["start"] <= tick + 1:
                return Action("wait", {})
        if actor["goal"]["progress"] < actor["goal"]["target"]:
            return Action("work", {"minutes": 1})
        return Action("wait", {})


class PolicyError(RuntimeError):
    pass


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


ACTION_CONTRACT = {
    "wait": {}, "move": {"location": "reachable location id"}, "work": {"minutes": "integer 1..60"},
    "say": {"text": "nonempty string, <=2000 characters", "target": "nearby actor id or null for room audience"},
    "tell": {"target": "nearby actor id", "source_event": "id of a known memory"},
    "invite": {"target": "nearby actor id", "start": "future integer tick", "end": "integer tick >start, <=start+60",
               "location": "known location id", "purpose": "nonempty string, <=500 characters"},
    "respond": {"invitation_id": "received pending invitation id", "accept": "boolean"},
    "cancel": {"invitation_id": "own open invitation id"},
}


class RemotePolicy:
    """Provider-neutral JSON gateway; credentials come from the host, not saves."""

    def __init__(self, endpoint: str, api_key: str = "", timeout: float = 10):
        url = parse.urlsplit(endpoint)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if url.scheme not in {"http", "https"} or (url.scheme == "http" and not local):
            raise ValueError("use HTTPS or a localhost HTTP gateway")
        if not url.hostname or url.username or url.password or url.fragment:
            raise ValueError("invalid gateway URL")
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
            raise ValueError("timeout must be 0..60 seconds")
        self.endpoint, self.api_key, self.timeout = endpoint, api_key, timeout
        self._opener = request.build_opener(_NoRedirect)

    def decide(self, context: dict) -> Action:
        body = canonical({"schema_version": 1, "actor_id": context["self"]["id"], "context": copy.deepcopy(context),
                          "action_contract": ACTION_CONTRACT,
                          "response_contract": {"kind": "action name", "params": "exact action fields; no actor id"}}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        req = request.Request(self.endpoint, body, headers, method="POST")
        try:
            with self._opener.open(req, timeout=self.timeout) as response:
                data = response.read(65537)
            if len(data) > 65536:
                raise PolicyError("response_too_large")
            return Action.parse(json.loads(data.decode("utf-8")))
        except (error.URLError, TimeoutError, OSError):
            raise PolicyError("gateway_unavailable") from None
        except (ValueError, TypeError, UnicodeError):
            raise PolicyError("invalid_gateway_response") from None
