from __future__ import annotations

import copy
import threading
from typing import Any

from .model import Action, Outcome, Rejected, canonical, digest


class Engine:
    """Single writer. Policies receive projections, never authoritative state."""

    def __init__(self, genesis: dict[str, Any]):
        self._lock = threading.RLock()
        # Optional runtime visibility rule supplied by the physical world. Journals
        # still contain explicit authorised audiences and remain replayable alone.
        self.proximity = None
        self.venue_resolver = None
        self.economy_handler = None
        self.economy_clock = None
        self.wardrobe_handler = None
        self.venue_completed = None
        self.social_handler = None
        self.social_clock = None
        self.city_clock = None
        self.pool_handler = None
        self.interaction_handler = None
        self.approach_handler = None
        self._genesis = copy.deepcopy(genesis)
        self._events: list[dict] = []
        self._chain = digest(self._genesis)
        self._state = self._initial_state(self._genesis)

    @staticmethod
    def _initial_state(genesis: dict) -> dict:
        if not isinstance(genesis, dict) or set(genesis) != {"locations", "actors"}:
            raise ValueError("invalid genesis")
        locations = genesis["locations"]
        if not isinstance(locations, dict) or not locations:
            raise ValueError("locations required")
        for location, neighbors in locations.items():
            if not isinstance(location, str) or not location or not isinstance(neighbors, list):
                raise ValueError("invalid location")
            if len(set(neighbors)) != len(neighbors):
                raise ValueError("duplicate neighbor")
            for neighbor in neighbors:
                if neighbor not in locations or location not in locations[neighbor] or neighbor == location:
                    raise ValueError("connections must be valid and symmetric")
        actors = {}
        if not isinstance(genesis["actors"], list) or not genesis["actors"]:
            raise ValueError("actors required")
        for spec in genesis["actors"]:
            if not isinstance(spec, dict) or set(spec) != {"id", "name", "age", "role", "location", "goal"}:
                raise ValueError("invalid actor schema")
            if not isinstance(spec["id"], str) or not spec["id"] or spec["id"] in actors:
                raise ValueError("invalid or duplicate actor id")
            if not isinstance(spec["name"], str) or not spec["name"]:
                raise ValueError("invalid name")
            if type(spec["age"]) is not int or spec["age"] < 18:
                raise ValueError("prototype characters must be adults")
            if spec["role"] not in {"agent", "player", "npc"} or spec["location"] not in locations:
                raise ValueError("invalid role or location")
            goal = spec["goal"]
            if not isinstance(goal, dict) or set(goal) != {"title", "target"}:
                raise ValueError("invalid goal schema")
            if not isinstance(goal["title"], str) or type(goal["target"]) is not int or goal["target"] < 0:
                raise ValueError("invalid goal")
            actors[spec["id"]] = {**copy.deepcopy(spec), "goal": {**goal, "progress": 0},
                                   "activity": "idle", "activity_ref": None, "busy_until": 0,
                                   "memories": [], "relationships": {},"gender":"male" if spec['role']=='player' else 'female'}
        return {"tick": 0, "actors": actors, "locations": copy.deepcopy(locations),
                "jobs": {}, "invitations": {}, "commands": {}}

    @property
    def tick(self) -> int:
        with self._lock:
            return self._state["tick"]

    @property
    def revision(self) -> int:
        with self._lock:
            return len(self._events)

    def agent_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(key for key, actor in self._state["actors"].items() if actor["role"] == "agent")

    def agent_views(self) -> dict[str, dict]:
        with self._lock:
            return {actor_id: self.view(actor_id) for actor_id in self.agent_ids()}

    def export_state(self) -> dict:
        """Administrative snapshot. Do not pass this to a model or player UI."""
        with self._lock:
            return copy.deepcopy({**self._state, "revision": len(self._events)})

    def view(self, actor_id: str, memory_limit: int = 40) -> dict:
        with self._lock:
            if type(memory_limit) is not int or not 1 <= memory_limit <= 200:
                raise ValueError("invalid memory limit")
            actor = self._state["actors"][actor_id]
            event_map = {event["id"]: event for event in self._events}
            own = {key: value for key, value in actor.items() if key not in {"memories", "relationships"}}
            neighbors = [{"id": other["id"], "name": other["name"], "activity": other["activity"]}
                         for other in self._state["actors"].values()
                         if other["id"] != actor_id and other["location"] == actor["location"]
                         and (self.proximity is None or self.proximity(actor_id, other["id"]))]
            memories = [{key: event_map[event_id][key] for key in ("id", "tick", "kind", "actor", "data")}
                        for event_id in actor["memories"][-memory_limit:]]
            relations = {other: ids[-10:] for other, ids in actor["relationships"].items()}
            invitations = [value for value in self._state["invitations"].values()
                           if actor_id in (value["sender"], value["recipient"])]
            return copy.deepcopy({"tick": self.tick, "revision": self.revision, "self": own,
                                  "nearby": neighbors, "paths": self._state["locations"][actor["location"]],
                                  "memories": memories, "relationships": relations,
                                  "invitations": invitations, "actions": sorted(self._schemas())})

    @staticmethod
    def _schemas() -> dict[str, set[str]]:
        from .social import SCHEMAS
        return {**SCHEMAS, "wait": set(), "interact": {"object"}, "approach_object": {"object"}, "move": {"location"}, "work": {"minutes"},
                "say": {"text", "target"}, "tell": {"target", "source_event"},
                "invite": {"target", "start", "end", "location", "purpose"},
                "respond": {"invitation_id", "accept"}, "cancel": {"invitation_id"}, "use": {"item"},
                "shift":set(),"craft":set(),"offer":{"item","quantity","price"},"buy":{"listing"},
                "buy_supply":{"item"},"consume":{"item"},"withdraw":{"listing"},"buy_clothes":{"item"},"wear":{"item"},"pool_change":set(),"pool_swim":set()}

    def expand_locations(self, graph):
        """Trusted map migration, journaled without replacing the old genesis."""
        with self._lock:
            current=self._state['locations']
            if graph==current: return
            if any(k not in graph or not set(v)<=set(graph[k]) for k,v in current.items()):
                raise ValueError('map migration cannot remove paths')
            self._initial_state({'locations':graph,'actors':self._genesis['actors']})
            self._emit('world_expanded',None,{'locations':graph},[],remember=False)

    def dispatch(self, actor_id: str, action: Action | dict, request_id: str,
                 expected_revision: int | None = None, expected_tick: int | None = None) -> Outcome:
        with self._lock:
            if not isinstance(actor_id, str) or actor_id not in self._state["actors"]:
                return Outcome(False, "unknown_actor")
            if not isinstance(request_id, str) or not request_id or len(request_id) > 160:
                return Outcome(False, "invalid_request_id")
            try:
                parsed = Action.parse(action.to_dict() if isinstance(action, Action) else action)
            except (ValueError, TypeError, OverflowError):
                return Outcome(False, "invalid_action_schema")
            fingerprint = digest(parsed.to_dict())
            cache_key = canonical([actor_id, request_id])
            cached = self._state["commands"].get(cache_key)
            if cached:
                if cached["fingerprint"] != fingerprint:
                    return Outcome(False, "idempotency_conflict")
                return Outcome(cached["accepted"], cached["reason"], tuple(cached["event_ids"]))
            if expected_revision is not None:
                if type(expected_revision) is not int or expected_revision != self.revision:
                    return Outcome(False, "stale_revision")
            if expected_tick is not None:
                if type(expected_tick) is not int or expected_tick != self.tick:
                    return Outcome(False, "stale_tick")
            previous_state, previous_chain, previous_count = copy.deepcopy(self._state), self._chain, self.revision
            try:
                try:
                    self._perform(actor_id, parsed)
                    accepted, reason = True, "ok"
                except Rejected as exc:
                    # Validation failures must not leave partial actions behind.
                    self._state, self._chain = copy.deepcopy(previous_state), previous_chain
                    del self._events[previous_count:]
                    accepted, reason = False, str(exc)
                result_ids = tuple(event["id"] for event in self._events[previous_count:])
                data = {"key": cache_key, "fingerprint": fingerprint, "accepted": accepted,
                        "reason": reason, "event_ids": list(result_ids)}
                self._emit("command_result", actor_id, data, [actor_id], remember=False)
                self.assert_consistent()
                return Outcome(accepted, reason, result_ids)
            except Exception:
                self._state, self._chain = previous_state, previous_chain
                del self._events[previous_count:]
                raise

    def _perform(self, actor_id: str, action: Action) -> None:
        schemas = self._schemas()
        if action.kind not in schemas or set(action.params) != schemas[action.kind]:
            raise Rejected("invalid_action_params")
        actor, params = self._state["actors"][actor_id], action.params
        if action.kind.startswith("group_"):
            if self.social_handler is None:raise Rejected("social_unavailable")
            self.social_handler(actor_id,action);return
        if actor["busy_until"] > self.tick and action.kind != "cancel":
            raise Rejected("actor_busy")
        if action.kind == "cancel" and actor["activity"] not in {"idle", "meeting"}:
            raise Rejected("actor_busy")
        if action.kind in {"say", "tell", "invite"}:
            target = params["target"]
            if action.kind == "say" and target is None:
                target = None
            elif not isinstance(target, str) or target == actor_id or target not in self._state["actors"]:
                raise Rejected("invalid_target")
            elif self._state["actors"][target]["location"] != actor["location"]:
                raise Rejected("target_not_here")
            elif self.proximity is not None and not self.proximity(actor_id, target):
                raise Rejected("target_too_far")
        if action.kind=='approach_object':
            if self.approach_handler is None:raise Rejected('interaction_unavailable')
            self.approach_handler(actor_id,action)
        elif action.kind=='interact':
            if self.interaction_handler is None:raise Rejected('interaction_unavailable')
            self.interaction_handler(actor_id,action)
        elif action.kind in {'pool_change','pool_swim'}:
            if self.pool_handler is None:raise Rejected('pool_unavailable')
            self.pool_handler(actor_id,action)
        elif action.kind in {'buy_clothes','wear'}:
            if self.wardrobe_handler is None:raise Rejected('wardrobe_unavailable')
            self.wardrobe_handler(actor_id,action)
        elif action.kind in {'shift','craft','offer','buy','buy_supply','consume','withdraw'}:
            if self.economy_handler is None:raise Rejected('economy_unavailable')
            self.economy_handler(actor_id,action)
        elif action.kind == "wait":
            self._set_activity(actor_id, "idle", self.tick + 1)
        elif action.kind == 'use':
            if self.venue_resolver is None: raise Rejected('facility_unavailable')
            data=self.venue_resolver(actor_id,params['item'])
            if self._conflict(actor_id,self.tick,self.tick+data['minutes']): raise Rejected('commitment_conflict')
            if actor.get('wallet',500)<data['price']: raise Rejected('insufficient_funds')
            self._emit('venue_started',actor_id,{**data,'ends_at':self.tick+data['minutes']},[actor_id])
            # Nearby observers see an action, not the reader's private knowledge.
            self._emit('venue_observed',actor_id,{'venue':data['venue'],'title':data['title'],'mode':data['mode']},self._at(actor['location'],actor_id))
        elif action.kind == "move":
            destination = params["location"]
            if not isinstance(destination, str) or destination not in self._state["locations"][actor["location"]]:
                raise Rejected("invalid_path")
            audience = set(self._at(actor["location"], actor_id) + self._at(destination, actor_id))
            self._emit("actor_moved", actor_id, {"from": actor["location"], "to": destination}, audience)
            self._set_activity(actor_id, "moving", self.tick + 1)
        elif action.kind == "work":
            minutes = params["minutes"]
            if type(minutes) is not int or not 1 <= minutes <= 60:
                raise Rejected("invalid_duration")
            if actor["goal"]["progress"] >= actor["goal"]["target"]:
                raise Rejected("goal_complete")
            if self._conflict(actor_id, self.tick, self.tick + minutes):
                raise Rejected("commitment_conflict")
            self._emit("work_started", actor_id, {"ends_at": self.tick + minutes, "minutes": minutes}, self._at(actor["location"], actor_id))
        elif action.kind == "say":
            text = params["text"]
            if not isinstance(text, str) or not text.strip() or len(text) > 2000:
                raise Rejected("invalid_text")
            audience = self._at(actor["location"], actor_id) if target is None else [actor_id, target]
            self._emit("message_spoken", actor_id, {"text": text, "target": target,
                                                     "epistemic_status": "statement_not_verified_fact"}, audience)
            self._set_activity(actor_id, "talking", self.tick + 1)
        elif action.kind == "tell":
            source_id = params["source_event"]
            if not isinstance(source_id, str) or source_id not in actor["memories"]:
                raise Rejected("source_not_known")
            source = next(event for event in self._events if event["id"] == source_id)
            summary = source["data"]["source"] if source["kind"] == "information_shared" else {
                "kind": source["kind"], "actor": source["actor"], "data": source["data"]}
            self._emit("information_shared", actor_id, {"target": target, "source_event": source_id,
                                                         "source": summary, "epistemic_status": "reported"}, [actor_id, target])
            self._set_activity(actor_id, "talking", self.tick + 1)
        elif action.kind == "invite":
            start, end = params["start"], params["end"]
            if type(start) is not int or type(end) is not int or start <= self.tick or not start < end <= start + 60:
                raise Rejected("invalid_interval")
            if not isinstance(params["location"], str) or params["location"] not in self._state["locations"]:
                raise Rejected("invalid_location")
            if not isinstance(params["purpose"], str) or not params["purpose"].strip() or len(params["purpose"]) > 500:
                raise Rejected("invalid_purpose")
            invitation = {"id": f"invite-{self.revision + 1:06d}", "sender": actor_id, "recipient": target,
                          "start": start, "end": end, "location": params["location"],
                          "purpose": params["purpose"], "status": "pending"}
            self._emit("invitation_created", actor_id, invitation, [actor_id, target])
            self._set_activity(actor_id, "talking", self.tick + 1)
        elif action.kind in {"respond", "cancel"}:
            invitation_id = params["invitation_id"]
            if not isinstance(invitation_id, str) or invitation_id not in self._state["invitations"]:
                raise Rejected("unknown_invitation")
            invitation = self._state["invitations"][invitation_id]
            parties = [invitation["sender"], invitation["recipient"]]
            if action.kind == "cancel":
                if actor_id not in parties:
                    raise Rejected("not_a_participant")
                if invitation["status"] not in {"pending", "accepted", "active"}:
                    raise Rejected("invitation_closed")
                status = "cancelled"
            else:
                if actor_id != invitation["recipient"]:
                    raise Rejected("not_the_recipient")
                if invitation["status"] != "pending" or self.tick >= invitation["start"]:
                    raise Rejected("invitation_closed")
                if type(params["accept"]) is not bool:
                    raise Rejected("invalid_accept")
                status = "accepted" if params["accept"] else "declined"
                if status == "accepted" and any(self._conflict(party, invitation["start"], invitation["end"])
                                               or self._state["actors"][party]["busy_until"] > invitation["start"] for party in parties):
                    raise Rejected("commitment_conflict")
            self._emit("invitation_status", actor_id, {"invitation_id": invitation_id, "status": status}, parties)
            if action.kind == "respond":
                self._set_activity(actor_id, "talking", self.tick + 1)

    def _conflict(self, actor_id: str, start: int, end: int) -> bool:
        from .social import group_conflict
        if group_conflict(self._state,actor_id,start,end):return True
        return any(actor_id in (inv["sender"], inv["recipient"]) and inv["status"] in {"accepted", "active"}
                   and start < inv["end"] and inv["start"] < end for inv in self._state["invitations"].values())

    def _at(self, location: str, observer: str | None = None) -> list[str]:
        return [actor["id"] for actor in self._state["actors"].values() if actor["location"] == location
                and (self.proximity is None or observer is None or actor["id"] == observer
                     or self.proximity(observer, actor["id"]))]

    def _set_activity(self, actor_id: str, activity: str, busy_until: int) -> None:
        self._emit("activity_set", actor_id, {"activity": activity, "busy_until": busy_until}, [actor_id], remember=False)

    def advance(self, minutes: int = 1, expected_tick: int | None = None) -> bool:
        with self._lock:
            if type(minutes) is not int or not 1 <= minutes <= 1440:
                raise ValueError("advance must be 1..1440 logical minutes")
            if expected_tick is not None and (type(expected_tick) is not int or expected_tick != self.tick):
                return False
            previous_state, previous_chain, previous_count = copy.deepcopy(self._state), self._chain, self.revision
            try:
                for _ in range(minutes):
                    self._emit("clock_advanced", None, {}, [], remember=False, tick=self.tick + 1)
                    for actor_id, actor in self._state['actors'].items():
                        job=actor.get('venue_job')
                        if job and job['ends_at']<=self.tick:
                            self._emit('venue_completed',actor_id,job,[actor_id])
                            if self.venue_completed:self.venue_completed(actor_id,job)
                    for actor_id, job in sorted(list(self._state["jobs"].items())):
                        if job["ends_at"] <= self.tick:
                            self._emit("work_completed", actor_id, {"minutes": job["minutes"]}, self._at(self._state["actors"][actor_id]["location"], actor_id))
                            self._emit("goal_progressed", actor_id, {"amount": job["minutes"]}, [actor_id])
                    if self.economy_clock:self.economy_clock()
                    if self.social_clock:self.social_clock()
                    if self.city_clock:self.city_clock()
                    for invitation in list(self._state["invitations"].values()):
                        parties = [invitation["sender"], invitation["recipient"]]
                        status = None
                        if invitation["status"] == "pending" and self.tick >= invitation["start"]:
                            status = "expired"
                        elif invitation["status"] == "accepted":
                            if self.tick >= invitation["end"]:
                                status = "missed"
                            elif (self.tick >= invitation["start"] and all(
                                    self._state["actors"][party]["location"] == invitation["location"]
                                    and self._state["actors"][party]["busy_until"] <= self.tick for party in parties)
                                    and (self.proximity is None or self.proximity(*parties))):
                                status = "active"
                        elif invitation["status"] == "active" and self.tick >= invitation["end"]:
                            status = "fulfilled"
                        if status:
                            self._emit("invitation_status", None, {"invitation_id": invitation["id"], "status": status}, parties)
                self.assert_consistent()
                return True
            except Exception:
                self._state, self._chain = previous_state, previous_chain
                del self._events[previous_count:]
                raise

    def _emit(self, kind: str, actor: str | None, data: dict, audience, remember: bool = True,
              tick: int | None = None) -> None:
        event = {"id": f"event-{len(self._events) + 1:08d}", "tick": self.tick if tick is None else tick,
                 "kind": kind, "actor": actor, "data": copy.deepcopy(data), "audience": sorted(set(audience)),
                 "remember": remember, "previous_hash": self._chain}
        event["hash"] = digest(event)
        self._apply(event)
        self._events.append(event)
        self._chain = event["hash"]

    def _apply(self, event: dict) -> None:
        state, kind, data, actor_id = self._state, event["kind"], event["data"], event["actor"]
        if kind=='component_profile':
            from .characters import apply_customization
            apply_customization(state,event)
        elif kind=='component_interacted':pass
        elif kind=='component_graph':self._state['locations']=copy.deepcopy(data['locations'])
        elif kind == 'world_expanded':
            self._initial_state({'locations':data['locations'],'actors':self._genesis['actors']})
            state['locations']=copy.deepcopy(data['locations'])
        elif kind.startswith('city_'):
            from .neighborhood import apply_city
            apply_city(state,event)
        elif kind.startswith('group_'):
            from .social import apply_social
            apply_social(state,event)
        elif kind=='character_profile_created':
            from .characters import apply_character
            apply_character(state,event)
        elif kind.startswith('wardrobe_'):
            from .wardrobe import apply_wardrobe
            apply_wardrobe(state,event)
        elif kind.startswith('economy_'):
            from .economy import apply_economy
            apply_economy(state,event)
        elif kind == 'venue_started':
            actor=state['actors'][actor_id]
            actor['wallet']=actor.get('wallet',500)-data['price']
            actor['venue_job']=copy.deepcopy(data)
            actor.update(activity='visiting',busy_until=data['ends_at'],activity_ref=event['id'])
        elif kind == 'venue_completed':
            actor=state['actors'][actor_id]; actor['venue_job']=None
            actor.setdefault('venue_progress',{})[data.get('progress_key',data['item'])]=data['part']+1
            actor.update(activity='idle',busy_until=self.tick,activity_ref=None)
        elif kind == 'venue_observed':
            pass
        elif kind == "clock_advanced":
            if event["tick"] != state["tick"] + 1:
                raise ValueError("clock must advance one minute")
            state["tick"] = event["tick"]
            for actor in state["actors"].values():
                if actor["busy_until"] <= self.tick and actor["activity"] not in {"working", "meeting"}:
                    actor["activity"], actor["activity_ref"] = "idle", None
        elif kind == "activity_set":
            state["actors"][actor_id].update(activity=data["activity"], busy_until=data["busy_until"], activity_ref=None)
        elif kind == "actor_moved":
            state["actors"][actor_id]["location"] = data["to"]
        elif kind == "work_started":
            state["jobs"][actor_id] = {"ends_at": data["ends_at"], "minutes": data["minutes"]}
            state["actors"][actor_id].update(activity="working", busy_until=data["ends_at"], activity_ref=event["id"])
        elif kind == "work_completed":
            del state["jobs"][actor_id]
            state["actors"][actor_id].update(activity="idle", busy_until=self.tick, activity_ref=None)
        elif kind == "goal_progressed":
            goal = state["actors"][actor_id]["goal"]
            goal["progress"] = min(goal["target"], goal["progress"] + data["amount"])
        elif kind == "invitation_created":
            state["invitations"][data["id"]] = copy.deepcopy(data)
        elif kind == "invitation_status":
            invitation = state["invitations"][data["invitation_id"]]
            invitation["status"] = data["status"]
            for party in (invitation["sender"], invitation["recipient"]):
                actor = state["actors"][party]
                if data["status"] == "active":
                    actor.update(activity="meeting", busy_until=invitation["end"], activity_ref=invitation["id"])
                elif actor["activity_ref"] == invitation["id"]:
                    actor.update(activity="idle", busy_until=self.tick, activity_ref=None)
        elif kind == "command_result":
            state["commands"][data["key"]] = copy.deepcopy(data)
        elif kind not in {"message_spoken", "information_shared"}:
            raise ValueError("unknown event kind")
        if event["remember"]:
            for party in event["audience"]:
                state["actors"][party]["memories"].append(event["id"])
                # Relationship history means interactions, not mere co-presence.
                if kind in {"message_spoken", "city_spoken", "information_shared", "invitation_created", "invitation_status", "group_spoken", "group_started"}:
                    for other in event["audience"]:
                        if other != party and (actor_id is None or actor_id in (party, other)):
                            state["actors"][party]["relationships"].setdefault(other, []).append(event["id"])

    def assert_consistent(self) -> None:
        with self._lock:
            events = {event["id"]: event for event in self._events}
            for actor_id, actor in self._state["actors"].items():
                if actor["location"] not in self._state["locations"] or not 0 <= actor["goal"]["progress"] <= actor["goal"]["target"]:
                    raise ValueError("invalid actor state")
                if (actor["activity"] == "working") != (actor_id in self._state["jobs"]):
                    raise ValueError("invalid work state")
                if actor.get('wallet',500)<0 or (actor.get('venue_job') and actor['busy_until']<actor['venue_job']['ends_at']):
                    raise ValueError('invalid venue state')
                if 'life' in actor:
                    life=actor['life']
                    if any(type(q) is not int or q<0 for q in life['inventory'].values()) or any(type(v) is not int or not 0<=v<=100 for v in life['needs'].values()):raise ValueError('invalid economy state')
                    if life['job'] and actor['busy_until']<life['job']['ends_at']:raise ValueError('invalid paid job')
                if 'wardrobe' in actor:
                    w=actor['wardrobe']
                    if w['wearing'] not in w['owned'] or (w['pending_wear'] is not None and w['pending_wear'] not in w['owned']):raise ValueError('invalid clothing ownership')
                    if any(k!=i['id'] or i['sfw'] is not True or not isinstance(i['prompt'],str) or len(i['prompt'])>600 for k,i in w['owned'].items()):raise ValueError('invalid outfit')
                for memory_id in actor["memories"]:
                    if memory_id not in events or actor_id not in events[memory_id]["audience"]:
                        raise ValueError("memory without authorized observation")
                for other, memory_ids in actor["relationships"].items():
                    if other not in self._state["actors"] or other == actor_id:
                        raise ValueError("invalid relationship")
                    if any(memory_id not in actor["memories"] or other not in events[memory_id]["audience"] for memory_id in memory_ids):
                        raise ValueError("invalid relationship evidence")
            for invitation in self._state["invitations"].values():
                if invitation["sender"] not in self._state["actors"] or invitation["recipient"] not in self._state["actors"]:
                    raise ValueError("invalid invitation participants")
            if 'economy' in self._state:
                for listing in self._state['economy']['listings'].values():
                    if listing['seller'] not in self._state['actors'] or type(listing['quantity']) is not int or listing['quantity']<1 or type(listing['price']) is not int or not 1<=listing['price']<=100:raise ValueError('invalid market stock')

            from .social import assert_social
            assert_social(self._state)

    def journal(self) -> dict:
        """Trusted local persistence envelope; includes private state, not UI data."""
        with self._lock:
            return copy.deepcopy({"schema_version": 1, "genesis": self._genesis, "events": self._events})

    @classmethod
    def replay(cls, journal: dict) -> Engine:
        if not isinstance(journal, dict) or set(journal) != {"schema_version", "genesis", "events"}:
            raise ValueError("invalid save schema")
        if type(journal["schema_version"]) is not int or journal["schema_version"] != 1 or not isinstance(journal["events"], list):
            raise ValueError("unsupported save version")
        engine = cls(journal["genesis"])
        fields = {"id", "tick", "kind", "actor", "data", "audience", "remember", "previous_hash", "hash"}
        for raw in journal["events"]:
            event = copy.deepcopy(raw)
            if not isinstance(event, dict) or set(event) != fields:
                raise ValueError("invalid event schema")
            if event["id"] != f"event-{engine.revision + 1:08d}" or event["previous_hash"] != engine._chain:
                raise ValueError("broken event order")
            if event["hash"] != digest({key: value for key, value in event.items() if key != "hash"}):
                raise ValueError("event checksum mismatch")
            if type(event["tick"]) is not int or event["tick"] != engine.tick + (event["kind"] == "clock_advanced"):
                raise ValueError("invalid event time")
            if event["actor"] is not None and event["actor"] not in engine._state["actors"]:
                raise ValueError("invalid event actor")
            if not isinstance(event["data"], dict) or type(event["remember"]) is not bool:
                raise ValueError("invalid event data")
            if not isinstance(event["audience"], list) or len(set(event["audience"])) != len(event["audience"]) or any(
                    party not in engine._state["actors"] for party in event["audience"]):
                raise ValueError("invalid event audience")
            engine._apply(event)
            engine._events.append(event)
            engine._chain = event["hash"]
        engine.assert_consistent()
        return engine
