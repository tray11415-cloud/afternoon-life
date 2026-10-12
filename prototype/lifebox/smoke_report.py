from __future__ import annotations

import json
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


class ReportingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.checks = []
        self.started_at = time.monotonic()

    def addSuccess(self, test):
        super().addSuccess(test)
        self.checks.append({"test": test.id(), "status": "passed", "description": test.shortDescription() or ""})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.checks.append({"test": test.id(), "status": "failed", "description": test.shortDescription() or ""})

    def addError(self, test, err):
        super().addError(test, err)
        self.checks.append({"test": test.id(), "status": "error", "description": test.shortDescription() or ""})


def write_report(result: ReportingResult, path: Path) -> None:
    report = {"generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
              "passed": result.wasSuccessful(), "tests_run": result.testsRun,
              "duration_seconds": round(time.monotonic() - result.started_at, 3),
              "scope": "世界底層、五模組、模型路由、CG 佇列、像素空間與九個公共場所、私人混合記憶檢索與分支隔離、角色語氣、xAI HTTP 契約及用量；公園需求恢復、完成打工才領薪、在家消耗材料創作、實際角色交易與庫存托管、消耗品、競爭最後庫存及十人無付費模型自主生活；SFW 服飾來源、獨立衣櫃、付款與所有權、回家換裝、存檔分支、穿著與 SD prompt／素材快取一致性及門口避讓；瀏覽器驗證另列報告",
              "checks": result.checks}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Smoke test 結果", "", f"測試時間：{report['generated_at']}",
             f"結果：{'通過' if report['passed'] else '失敗'} · {report['tests_run']} 項 · {report['duration_seconds']} 秒", "",
             report["scope"], "", "| 測試 | 結果 |", "| --- | --- |"]
    lines.extend(f"| {item['description'] or item['test']} | {item['status']} |" for item in result.checks)
    lines.extend(["", "## 尚未驗證", "", "- 長期個性持續性、關係演化及成熟的故事品質；實際 Stable Diffusion 生成效果。",
                  "- 長期遊玩品質、圖像與語音演出、多人連線和正式版部署。",
                  "- 像素介面已製作，真實模型及瀏覽器檢查另列報告；成人入口停用，一般 CG 接口尚未連接真實 SD 服務。",
                  "- CG 佇列及素材登錄仍為程序內狀態；世界、像素位置及字詞記憶索引與 xAI 用量已分別持久保存。語意模型未連接。",
                  "- 本地存檔包含完整私人狀態，不應直接提供給角色模型或玩家介面。", ""])
    path.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
