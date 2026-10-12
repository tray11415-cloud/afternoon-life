from __future__ import annotations

from .channels import CHANNEL_LABELS
from .engine import Engine
from .media import AssetCatalog, CGPrompt, RenderQueue
from .model import Action, Outcome, digest
from .routing import ModelRouter, Task


class GameInterface:
    """Presentation/controller boundary, not a graphical or network UI."""

    def __init__(self, engine: Engine, router: ModelRouter, queue: RenderQueue | None = None,
                 assets: AssetCatalog | None = None):
        self.engine, self.router, self.queue, self.assets = engine, router, queue, assets

    def scene(self, actor_id: str) -> dict:
        view = self.engine.view(actor_id)
        return self._scene_from(view)

    @staticmethod
    def _scene_from(view: dict) -> dict:
        # CG gets visual facts only. No goals, private memories or relationship history.
        return {"location": view["self"]["location"],
                "people": [{"id": view["self"]["id"], "name": view["self"]["name"], "activity": view["self"]["activity"]},
                           *view["nearby"]]}

    def screen(self, actor_id: str) -> dict:
        view = self.engine.view(actor_id)
        scene = self._scene_from(view)
        jobs = self.queue.visible_jobs(actor_id) if self.queue else []
        for job in jobs:
            job["current_scene"] = digest(job["scene"]) == digest(scene)
        return {"channels": {channel.value: label for channel, label in CHANNEL_LABELS.items()},
                "world": view, "scene": scene, "cg_jobs": jobs,
                "external_assets": self.assets.visible_assets(actor_id) if self.assets else []}

    def act(self, actor_id: str, action: Action | dict, request_id: str, expected_revision: int | None = None) -> Outcome:
        return self.engine.dispatch(actor_id, action, request_id, expected_revision=expected_revision)

    def dialogue(self, actor_id: str, target: str | None, request_id: str, importance: str = "normal") -> Outcome:
        view = self.engine.view(actor_id)
        if view["self"]["busy_until"] > view["tick"]:
            return Outcome(False, "actor_busy")
        if target is not None and target not in {person["id"] for person in view["nearby"]}:
            return Outcome(False, "target_not_here")
        text = self.router.request(Task.DIALOGUE, {"actor_view": view, "target": target}, importance)
        return self.engine.dispatch(actor_id, Action("say", {"text": text, "target": target}), request_id,
                                    expected_revision=view["revision"], expected_tick=view["tick"])

    def request_cg(self, actor_id: str, importance: str = "normal", seed: int = 0) -> str:
        if self.queue is None:
            raise ValueError("CG renderer is not configured")
        scene = self.scene(actor_id)
        prompt = self.router.request(Task.CG_PROMPT, scene, importance)
        return self.queue.submit(CGPrompt(prompt, seed=seed), actor_id, scene)

    def attach_existing_asset(self, actor_id: str, relative_file: str) -> str:
        self.engine.view(actor_id)
        if self.assets is None:
            raise ValueError("asset catalog is not configured")
        return self.assets.register(relative_file, (actor_id,))
