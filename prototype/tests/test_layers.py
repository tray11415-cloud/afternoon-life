from __future__ import annotations

import base64
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from lifebox import Action, Engine
from lifebox.channels import Channel
from lifebox.config import load_router
from lifebox.fixtures import neutral_world
from lifebox.interface import GameInterface
from lifebox.media import AssetCatalog, CGPrompt, MediaError, RenderQueue, StableDiffusionRenderer
from lifebox.model import canonical
from lifebox.policies import RoutinePolicy
from lifebox.routing import ModelRouter, Provider, RemoteTextBackend, RoutedPolicy, RouterError, Task, fixture_router
from lifebox.runtime import Runtime

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+cWZkAAAAASUVORK5CYII=")
A, B = "member-01", "member-02"


class CountingBackend(RoutinePolicy):
    def __init__(self, text="測試回覆", fail=False):
        self.text, self.fail, self.calls = text, fail, []

    def generate(self, task, context):
        self.calls.append((task, context))
        if self.fail:
            raise RuntimeError("PRIVATE-KEY-IN-EXCEPTION")
        return self.text


class LayerSmoke(unittest.TestCase):
    def setUp(self):
        self.engine = Engine(neutral_world())
        base = Path(os.environ.get("LIFE_TEST_WORKDIR", str(Path(__file__).resolve().parents[2] / "work"))).resolve()
        base.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="layers-", dir=base)
        self.temp = Path(self.temporary.name).resolve()
        self.assertTrue(self.temp.is_relative_to(base))

    def tearDown(self):
        self.temporary.cleanup()

    def test_five_channels_and_interface_without_model_calls(self):
        """五個模組可並存，介面讀取本身不呼叫模型。"""
        router = fixture_router()
        screen = GameInterface(self.engine, router).screen("player")
        self.assertEqual(set(screen["channels"]), {channel.value for channel in Channel})
        self.assertEqual(screen["world"]["self"]["id"], "player")
        self.assertNotIn("測試個人事項01", canonical(screen))
        self.assertTrue(all(item["calls"] == 0 for item in router.usage().values()))

    def test_normal_and_important_dialogue_use_different_backends(self):
        """日常與重要對話可分別路由到不同模型。"""
        local, cloud = CountingBackend("local"), CountingBackend("cloud")
        router = ModelRouter({"local": Provider(local, "local", 5), "cloud": Provider(cloud, "cloud", 1)},
                             {(Task.DIALOGUE, "normal"): ("local",), (Task.DIALOGUE, "important"): ("cloud", "local")})
        self.assertEqual(router.request(Task.DIALOGUE, {"turn": 1}), "local")
        self.assertEqual(router.request(Task.DIALOGUE, {"turn": 2}, "important"), "cloud")
        self.assertEqual(router.request(Task.DIALOGUE, {"turn": 3}, "important"), "local")
        self.assertEqual(router.usage()["cloud"]["calls"], 1)

    def test_cache_does_not_consume_call_budget(self):
        """相同輸入使用快取，不再消耗模型呼叫額度。"""
        backend = CountingBackend()
        router = ModelRouter({"model": Provider(backend, "local", 1)}, {(Task.DIALOGUE, "normal"): ("model",)})
        first = router.request(Task.DIALOGUE, {"turn": 1})
        self.assertEqual(router.request(Task.DIALOGUE, {"turn": 1}), first)
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(router.usage()["model"]["cache_hits"], 1)
        with self.assertRaises(RouterError):
            router.request(Task.DIALOGUE, {"turn": 2})

    def test_failed_backend_uses_only_configured_fallback(self):
        """模型故障只使用指定備援，不外洩錯誤中的憑證。"""
        first, second = CountingBackend(fail=True), CountingBackend("backup")
        router = ModelRouter({"first": Provider(first, "cloud", 1), "second": Provider(second, "local", 5)},
                             {(Task.DIALOGUE, "normal"): ("first", "second")})
        self.assertEqual(router.request(Task.DIALOGUE, {}), "backup")
        self.assertEqual(router.usage()["first"]["failures"], 1)
        self.assertNotIn("PRIVATE-KEY", canonical(router.usage()))

    def test_assets_and_interface_have_no_generation_route(self):
        """既有媒體與介面模組沒有 prompt 或模型生成路由。"""
        router = fixture_router()
        for channel in (Channel.EXTERNAL_MEDIA, Channel.INTERFACE):
            with self.assertRaises(RouterError):
                router.request(channel.value, {})
        self.assertTrue(all(item["calls"] == 0 for item in router.usage().values()))

    def test_routed_runtime_retains_ten_agent_independence(self):
        """模型路由加入後，十名角色仍各自完成生活事項。"""
        router = fixture_router()
        results = Runtime(self.engine, RoutedPolicy(router)).run(8)
        self.assertTrue(all(result["accepted"] for result in results))
        self.assertEqual(router.usage()["native"]["calls"], 50)
        self.assertEqual(router.usage()["dialogue_fixture"]["calls"], 0)
        self.assertTrue(all(self.engine.view(actor)["self"]["goal"]["progress"] == 5 for actor in self.engine.agent_ids()))

    def test_planned_speech_uses_dialogue_backend(self):
        """行動模型提出說話意圖後，台詞交給對話模型產生。"""
        self.engine.dispatch(A, Action("move", {"location": "shared"}), "bring")
        self.engine.advance()
        class Planner:
            def decide(self, context):
                return Action("say", {"text": "問候的意圖", "target": "player"})
        dialogue = CountingBackend("由對話模型產生的台詞")
        router = ModelRouter({"planner": Provider(Planner()), "dialogue": Provider(dialogue)},
                             {(Task.ACTIVITY, "normal"): ("planner",), (Task.DIALOGUE, "normal"): ("dialogue",)})
        action = RoutedPolicy(router).decide(self.engine.view(A))
        self.assertEqual(action.params["text"], "由對話模型產生的台詞")
        self.assertEqual(len(dialogue.calls), 1)
        self.assertTrue(self.engine.dispatch(A, action, "speak").accepted)

    def test_dialogue_preflight_and_world_consequences(self):
        """對話先檢查接觸條件，成功後仍由世界留下事件。"""
        router = fixture_router()
        interface = GameInterface(self.engine, router)
        self.assertFalse(interface.dialogue(A, "player", "not-here").accepted)
        self.assertEqual(router.usage()["dialogue_fixture"]["calls"], 0)
        self.engine.dispatch(A, Action("move", {"location": "shared"}), "bring")
        self.engine.advance()
        self.assertTrue(interface.dialogue(A, "player", "speak").accepted)
        self.assertIn("這是一句測試回覆", canonical(self.engine.view("player")))
        self.assertNotIn("這是一句測試回覆", canonical(self.engine.view(B)))

    def test_visual_projection_omits_private_goals_and_memories(self):
        """CG prompt 只取得視覺場景，不取得私人目標與記憶。"""
        self.engine.dispatch(A, Action("move", {"location": "shared"}), "bring")
        self.engine.advance()
        self.engine.dispatch("player", Action("say", {"text": "private-cg-token", "target": A}), "secret")
        scene = GameInterface(self.engine, fixture_router()).scene(A)
        self.assertNotIn("private-cg-token", canonical(scene))
        self.assertNotIn("測試個人事項", canonical(scene))
        self.assertEqual(scene["location"], "shared")

    def test_rendering_does_not_block_world_or_leak_other_jobs(self):
        """背景 CG 生成期間世界能推進，其他角色看不到私人工作。"""
        entered, release = threading.Event(), threading.Event()
        class SlowRenderer:
            def render(self, prompt):
                entered.set()
                if not release.wait(timeout=3):
                    raise RuntimeError("test timeout")
                return {"asset_id": "fixture"}
        queue = RenderQueue(SlowRenderer(), capacity=1)
        try:
            interface = GameInterface(self.engine, fixture_router(), queue)
            job = interface.request_cg(A)
            self.assertTrue(entered.wait(timeout=1))
            before = self.engine.export_state()["actors"]
            self.engine.advance(3)
            self.assertEqual(self.engine.tick, 3)
            self.assertEqual(before, self.engine.export_state()["actors"])
            self.assertEqual(interface.screen(B)["cg_jobs"], [])
            with self.assertRaises(MediaError):
                queue.status(job, B)
            with self.assertRaises(MediaError):
                queue.submit(CGPrompt("different ordinary scene"), A, {})
            release.set()
            queue.close()
            self.assertEqual(queue.status(job, A)["status"], "ready")
        finally:
            release.set()
            queue.close()

    def test_same_render_job_is_not_enqueued_twice(self):
        """相同角色、場景與生成參數不會重複排入 CG 工作。"""
        class Renderer:
            calls = 0
            def render(self, prompt):
                self.calls += 1
                return {"asset_id": "fixture"}
        renderer = Renderer()
        queue = RenderQueue(renderer)
        try:
            prompt = CGPrompt("ordinary shared room")
            first = queue.submit(prompt, A, {"location": "shared"})
            second = queue.submit(prompt, A, {"location": "shared"})
            queue.close()
            self.assertEqual(first, second)
            self.assertEqual(renderer.calls, 1)
        finally:
            queue.close()

    def test_render_failure_does_not_mutate_world(self):
        """生成失敗只影響媒體工作，不改動世界或曝露錯誤內容。"""
        class Renderer:
            def render(self, prompt):
                raise RuntimeError("PRIVATE-KEY")
        queue = RenderQueue(Renderer())
        try:
            before = self.engine.export_state()
            interface = GameInterface(self.engine, fixture_router(), queue)
            job = interface.request_cg(A)
            queue.close()
            status = queue.status(job, A)
            self.assertEqual(status["status"], "failed")
            self.assertNotIn("PRIVATE-KEY", canonical(status))
            self.assertEqual(before, self.engine.export_state())
        finally:
            queue.close()

    def test_external_artwork_is_scoped_and_never_generated(self):
        """自行提供的圖片只登錄與呈現，無模型呼叫，且不允許越出素材目錄。"""
        root = self.temp / "assets"
        root.mkdir()
        (root / "fixture.png").write_bytes(PNG)
        (self.temp / "outside.png").write_bytes(PNG)
        router = fixture_router()
        interface = GameInterface(self.engine, router, assets=AssetCatalog(root))
        asset = interface.attach_existing_asset(A, "fixture.png")
        self.assertEqual(interface.screen(A)["external_assets"][0]["asset_id"], asset)
        self.assertEqual(interface.screen(B)["external_assets"], [])
        with self.assertRaises(ValueError):
            interface.attach_existing_asset(A, "../outside.png")
        self.assertTrue(all(item["calls"] == 0 for item in router.usage().values()))

    def test_completed_image_is_marked_old_after_scene_changes(self):
        """場景變更後，舊 CG 會標記為歷史場景，不能冒充當前畫面。"""
        class Renderer:
            def render(self, prompt):
                return {"asset_id": "fixture"}
        queue = RenderQueue(Renderer())
        try:
            interface = GameInterface(self.engine, fixture_router(), queue)
            interface.request_cg(A)
            queue.close()
            self.assertTrue(interface.screen(A)["cg_jobs"][0]["current_scene"])
            self.engine.dispatch(A, Action("move", {"location": "shared"}), "move")
            self.assertFalse(interface.screen(A)["cg_jobs"][0]["current_scene"])
        finally:
            queue.close()


class MediaGatewaySmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.server.requests.append((self.path, data))
                if self.path == "/sdapi/v1/txt2img":
                    image = b"not-an-image" if data["prompt"] == "invalid-test" else PNG
                    response = {"images": [base64.b64encode(image).decode()], "parameters": data, "info": "fixture"}
                elif self.path == "/bad-text":
                    response = {"text": "bad", "actor": B}
                else:
                    response = {"text": "模型閘道的測試文字"}
                raw = json.dumps(response, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            def log_message(self, *args):
                pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.requests = []
        cls.thread = threading.Thread(target=lambda: cls.server.serve_forever(poll_interval=0.02), daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        base = Path(os.environ.get("LIFE_TEST_WORKDIR", str(Path(__file__).resolve().parents[2] / "work"))).resolve()
        base.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="media-gateway-", dir=base)
        self.temp = Path(self.temporary.name).resolve()
        self.assertTrue(self.temp.is_relative_to(base))

    def tearDown(self):
        self.temporary.cleanup()

    def test_sd_adapter_http_contract_and_disk_cache(self):
        """一般 CG 的 SD HTTP 契約、圖片落盤與快取可正常串接。"""
        renderer = StableDiffusionRenderer(self.url, self.temp / "cg")
        prompt = CGPrompt("ordinary shared room", seed=7)
        before = len(self.server.requests)
        first = renderer.render(prompt)
        second = renderer.render(prompt)
        self.assertEqual(Path(first["path"]).read_bytes(), PNG)
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(len(self.server.requests) - before, 1)
        path, payload = self.server.requests[-1]
        self.assertEqual(path, "/sdapi/v1/txt2img")
        self.assertEqual(payload["seed"], 7)
        self.assertEqual(payload["batch_size"], 1)

    def test_sd_adapter_rejects_bad_images_and_parameters(self):
        """SD 的非法回覆與生成參數被拒絕，不留下假圖片。"""
        renderer = StableDiffusionRenderer(self.url, self.temp / "cg")
        with self.assertRaises(MediaError):
            renderer.render(CGPrompt("invalid-test"))
        with self.assertRaises(ValueError):
            renderer.render(CGPrompt("ordinary room", seed=-1))
        with self.assertRaises(ValueError):
            renderer.render(CGPrompt("ordinary room", width=123))
        self.assertEqual(list(self.temp.rglob("*.png")), [])

    def test_text_gateway_contract_and_validation(self):
        """獨立對話與 CG prompt 閘道使用文字契約，拒絕額外行動者欄位。"""
        backend = RemoteTextBackend(self.url + "/text")
        self.assertEqual(backend.generate(Task.DIALOGUE, {"actor_view": Engine(neutral_world()).view(A)}), "模型閘道的測試文字")
        self.assertEqual(self.server.requests[-1][1]["task"], "dialogue")
        self.assertEqual(self.server.requests[-1][1]["actor_id"], A)
        with self.assertRaises(RouterError):
            RemoteTextBackend(self.url + "/bad-text").generate(Task.DIALOGUE, {})

    def test_model_config_loads_separate_task_routes(self):
        """JSON 設定能分別配置行動、對話與 CG prompt 模型。"""
        config = {"schema_version": 1,
                  "providers": {"rules": {"kind": "rules", "scope": "native"},
                                "text": {"kind": "text_gateway", "scope": "local", "endpoint_env": "TEST_LIFE_ENDPOINT", "max_calls": 2}},
                  "routes": [{"task": task, "importance": importance, "providers": ["rules" if task == "activity" else "text"]}
                             for task in ("activity", "dialogue", "cg_prompt") for importance in ("normal", "important")]}
        path = self.temp / "models.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        with mock.patch.dict(os.environ, {"TEST_LIFE_ENDPOINT": self.url + "/text"}):
            router = load_router(path)
        self.assertEqual(router.request(Task.DIALOGUE, {}), "模型閘道的測試文字")
        self.assertEqual(router.request(Task.CG_PROMPT, {}), "模型閘道的測試文字")
        self.assertEqual(router.usage()["text"]["calls"], 2)
