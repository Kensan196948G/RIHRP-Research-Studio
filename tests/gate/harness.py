"""品質ゲート実行用の証跡ハーネス。

各テストは QA ワークベンチの testcase id を持ち、実行した手順・観測値・
仕様との差異を JSON に残す。合否は pytest と JUnit XML の両方で読める。
"""

from __future__ import annotations

import json
import pathlib
import time
from typing import Any

OUT_DIR = pathlib.Path(__file__).resolve().parents[2] / "tmp" / "gate-20261108" / "evidence"


class Case:
    """1 テストケース分の実行記録。"""

    def __init__(self, tc_id: str, title: str) -> None:
        self.tc_id = tc_id
        self.title = title
        self.started = time.monotonic()
        self.observations: list[dict[str, Any]] = []
        self.deviations: list[str] = []
        self.skips: list[str] = []
        self.failures: list[str] = []

    def step(self, name: str, **data: Any) -> None:
        self.observations.append({"step": name, **data})

    def expect(self, condition: bool, message: str) -> None:
        if not condition:
            self.failures.append(message)

    def deviation(self, message: str) -> None:
        """仕様（ケース記述）と実装の差異。製品不具合とは限らない。"""
        self.deviations.append(message)

    def skip(self, message: str) -> None:
        self.skips.append(message)

    def finish(self) -> None:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "testcase_id": self.tc_id,
            "title": self.title,
            "outcome": "pass" if not self.failures else "fail",
            "duration_ms": int((time.monotonic() - self.started) * 1000),
            "failures": self.failures,
            "deviations": self.deviations,
            "skips": self.skips,
            "observations": self.observations,
            "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        (OUT_DIR / f"{self.tc_id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        assert not self.failures, " / ".join(self.failures)
