from __future__ import annotations

import base64
import copy
import json
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib import error, parse, request

from .model import canonical, digest
from .policies import _NoRedirect


class MediaError(RuntimeError):
    pass


@dataclass(frozen=True)
class CGPrompt:
    prompt: str
    negative_prompt: str = ""
    seed: int = 0
    width: int = 512
    height: int = 512
    steps: int = 20

    def payload(self) -> dict:
        if not isinstance(self.prompt, str) or not 0 < len(self.prompt.strip()) <= 8000:
            raise ValueError("invalid prompt")
        if not isinstance(self.negative_prompt, str) or len(self.negative_prompt) > 8000:
            raise ValueError("invalid negative prompt")
        if type(self.seed) is not int or not 0 <= self.seed <= 4294967295:
            raise ValueError("use a fixed nonnegative seed")
        if any(type(value) is not int or not 64 <= value <= 2048 or value % 8 for value in (self.width, self.height)):
            raise ValueError("invalid dimensions")
        if type(self.steps) is not int or not 1 <= self.steps <= 150:
            raise ValueError("invalid steps")
        return {**asdict(self), "batch_size": 1, "n_iter": 1}


class StableDiffusionRenderer:
    """General illustration adapter for the WebUI txt2img JSON API."""

    def __init__(self, base_url: str, output_root: str | Path, api_key: str = "", timeout: float = 120):
        url = parse.urlsplit(base_url)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if url.scheme not in {"http", "https"} or (url.scheme == "http" and not local):
            raise ValueError("use HTTPS or localhost HTTP")
        if not url.hostname or url.username or url.password or url.query or url.fragment or not 0 < timeout <= 300:
            raise ValueError("invalid renderer configuration")
        self.endpoint = base_url.rstrip("/") + "/sdapi/v1/txt2img"
        self.output_root = Path(output_root).resolve()
        self.api_key, self.timeout = api_key, timeout
        self._opener = request.build_opener(_NoRedirect)

    def render(self, prompt: CGPrompt) -> dict:
        payload = prompt.payload()
        asset_id = digest({"renderer": self.endpoint, "payload": payload})
        path = self.output_root / (asset_id + ".png")
        if path.is_file() and path.stat().st_size <= 8 * 1024 * 1024:
            with path.open("rb") as stream:
                if stream.read(8) == b"\x89PNG\r\n\x1a\n":
                    return {"asset_id": asset_id, "path": str(path), "cache_hit": True}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        try:
            body = canonical(payload).encode("utf-8")
            req = request.Request(self.endpoint, body, headers, method="POST")
            with self._opener.open(req, timeout=self.timeout) as response:
                raw = response.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                raise ValueError("response too large")
            data = json.loads(raw.decode("utf-8"))
            images = data.get("images") if isinstance(data, dict) else None
            if not isinstance(images, list) or not images or not isinstance(images[0], str):
                raise ValueError("missing image")
            encoded = images[0]
            if encoded.startswith("data:image/png;base64,"):
                encoded = encoded.split(",", 1)[1]
            image = base64.b64decode(encoded, validate=True)
            if not 8 < len(image) <= 8 * 1024 * 1024 or not image.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("invalid PNG response")
        except (error.URLError, TimeoutError, OSError, ValueError, TypeError, UnicodeError):
            raise MediaError("render_failed") from None
        self.output_root.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=asset_id + ".", suffix=".tmp", dir=self.output_root)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(image)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return {"asset_id": asset_id, "path": str(path), "cache_hit": False}


class RenderQueue:
    """Bounded background jobs. No worker is allowed to mutate world state."""

    def __init__(self, renderer, workers: int = 1, capacity: int = 16):
        if type(workers) is not int or not 1 <= workers <= 4 or type(capacity) is not int or capacity < workers:
            raise ValueError("invalid queue size")
        self.renderer, self.capacity = renderer, capacity
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="cg-render")
        self._jobs, self._lock, self._closed = {}, threading.Lock(), False

    def submit(self, prompt: CGPrompt, owner: str, scene: dict) -> str:
        payload = prompt.payload()
        if not isinstance(owner, str) or not owner:
            raise ValueError("invalid owner")
        job_id = digest({"owner": owner, "scene": scene, "payload": payload})
        with self._lock:
            if self._closed:
                raise MediaError("queue_closed")
            if job_id in self._jobs:
                return job_id
            if sum(not job["future"].done() for job in self._jobs.values()) >= self.capacity:
                raise MediaError("queue_full")
            future = self._executor.submit(self.renderer.render, copy.deepcopy(prompt))
            self._jobs[job_id] = {"future": future, "owner": owner, "scene": copy.deepcopy(scene)}
        return job_id

    def status(self, job_id: str, viewer: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job["owner"] != viewer:
                raise MediaError("job_not_visible")
            result = {"job_id": job_id, "channel": "cg", "scene": copy.deepcopy(job["scene"])}
            future = job["future"]
            if not future.done():
                return {**result, "status": "running" if future.running() else "queued"}
            try:
                asset = future.result()
                if not isinstance(asset, dict) or not isinstance(asset.get("asset_id"), str):
                    raise ValueError("invalid asset")
                return {**result, "status": "ready", "asset_id": asset["asset_id"]}
            except Exception:
                return {**result, "status": "failed", "reason": "render_failed"}

    def visible_jobs(self, viewer: str) -> list[dict]:
        with self._lock:
            ids = [job_id for job_id, job in self._jobs.items() if job["owner"] == viewer]
        return [self.status(job_id, viewer) for job_id in ids]

    def close(self, wait: bool = True) -> None:
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=True)


class AssetCatalog:
    """Neutral importer for existing local artwork, independent of generation."""

    def __init__(self, root: str | Path):
        self.root, self._assets, self._lock = Path(root).resolve(), {}, threading.Lock()

    def register(self, relative_file: str, viewers: tuple[str, ...]) -> str:
        if not isinstance(relative_file, str) or not viewers or any(not isinstance(viewer, str) or not viewer for viewer in viewers):
            raise ValueError("invalid asset registration")
        path = (self.root / relative_file).resolve()
        if not path.is_relative_to(self.root) or not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("asset must be an existing image inside assets")
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("asset too large")
        asset_id = digest({"relative_file": path.relative_to(self.root).as_posix(), "viewers": sorted(set(viewers))})
        with self._lock:
            self._assets[asset_id] = {"asset_id": asset_id, "channel": "external_media",
                                      "relative_file": path.relative_to(self.root).as_posix(), "viewers": tuple(sorted(set(viewers)))}
        return asset_id

    def visible_assets(self, viewer: str) -> list[dict]:
        with self._lock:
            return [{key: value for key, value in asset.items() if key != "viewers"}
                    for asset in self._assets.values() if viewer in asset["viewers"]]
