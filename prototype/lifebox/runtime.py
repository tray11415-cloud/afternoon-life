from __future__ import annotations

from .engine import Engine
from .model import Action
from .policies import Policy


class Runtime:
    def __init__(self, engine: Engine, policy: Policy):
        self.engine, self.policy = engine, policy

    def step(self) -> list[dict]:
        # All decisions use projections from one world moment. Application is
        # serialized and revalidates against current authoritative state.
        contexts = self.engine.agent_views()
        actor_ids = sorted(contexts)
        if actor_ids:
            offset = self.engine.tick % len(actor_ids)
            actor_ids = actor_ids[offset:] + actor_ids[:offset]
        decisions, results = [], []
        for actor_id in actor_ids:
            context = contexts[actor_id]
            actor = context["self"]
            if actor["busy_until"] > context["tick"]:
                continue
            has_plan = any(inv["status"] in {"pending", "accepted"} for inv in context["invitations"])
            if actor["goal"]["progress"] >= actor["goal"]["target"] and not has_plan:
                continue
            try:
                raw = self.policy.decide(context)
                action = Action.parse(raw.to_dict() if isinstance(raw, Action) else raw)
            except Exception:
                # Log a stable error code, never provider exception text or credentials.
                results.append({"actor": actor_id, "accepted": False, "reason": "policy_failed", "event_ids": []})
                continue
            decisions.append((actor_id, context["tick"], action))
        for actor_id, tick, action in decisions:
            outcome = self.engine.dispatch(actor_id, action, f"runtime:{tick}:{actor_id}", expected_tick=tick)
            results.append({"actor": actor_id, **outcome.to_dict()})
        observed_tick = next(iter(contexts.values()))["tick"] if contexts else self.engine.tick
        self.engine.advance(expected_tick=observed_tick)
        return results

    def run(self, minutes: int) -> list[dict]:
        if type(minutes) is not int or not 1 <= minutes <= 1440:
            raise ValueError("run must be 1..1440 logical minutes")
        results = []
        for _ in range(minutes):
            results.extend(self.step())
        return results
