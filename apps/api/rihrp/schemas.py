"""入力スキーマ。"""

from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

MAX_CONTENT_BYTES = 1024 * 1024
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _require_nonempty(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("空白だけの値は使用できません。")
    return stripped


def _require_email(value: str) -> str:
    stripped = value.strip().lower()
    if not EMAIL_RE.match(stripped):
        raise ValueError("メールアドレスの形式が不正です。")
    return stripped


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return value.strip().lower()


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=12, max_length=200)


class ProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=5000)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _require_nonempty(value)

    @field_validator("summary")
    @classmethod
    def _summary(cls, value: str) -> str:
        return value.strip()


class ProjectPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=5000)
    status: Literal["active", "archived"] | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return None if value is None else _require_nonempty(value)

    @field_validator("summary")
    @classmethod
    def _summary(cls, value: str | None) -> str | None:
        return None if value is None else value.strip()


class SourceIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    kind: Literal["url", "doi", "text"] = "text"
    origin: str = Field(default="", max_length=1000)
    content: str = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _require_nonempty(value)

    @field_validator("origin")
    @classmethod
    def _origin(cls, value: str) -> str:
        return value.strip()

    @field_validator("content")
    @classmethod
    def _content_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_CONTENT_BYTES:
            raise ValueError("本文は 1 MiB 以下にしてください。")
        return value


class ClaimIn(BaseModel):
    text: str = Field(min_length=10, max_length=2000)

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 10:
            raise ValueError("主張は 10 文字以上にしてください。")
        return stripped


class ClaimPatch(BaseModel):
    text: str = Field(min_length=10, max_length=2000)

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 10:
            raise ValueError("主張は 10 文字以上にしてください。")
        return stripped


class EvidenceIn(BaseModel):
    source_id: str = Field(min_length=1, max_length=36)
    quote: str = Field(default="", max_length=500)
    note: str = Field(default="", max_length=1000)


class ReportIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _require_nonempty(value)


class ParagraphIn(BaseModel):
    id: str | None = None
    text: str = Field(default="", max_length=20000)
    claimIds: list[str] = Field(default_factory=list)


class SectionIn(BaseModel):
    id: str | None = None
    heading: str = Field(default="", max_length=300)
    paragraphs: list[ParagraphIn] = Field(default_factory=list)


class ReportContentIn(BaseModel):
    sections: list[SectionIn] = Field(default_factory=list)


class ReportUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: ReportContentIn | None = None
    note: str = Field(default="", max_length=300)
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return None if value is None else _require_nonempty(value)


class ReviewIn(BaseModel):
    decision: Literal["approved", "changes_requested"]
    comment: str = Field(default="", max_length=5000)


class UserIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    name: str = Field(min_length=1, max_length=120)
    role: Literal["admin", "editor", "reviewer", "viewer"]
    password: str = Field(min_length=12, max_length=200)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _require_email(value)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _require_nonempty(value)


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Literal["admin", "editor", "reviewer", "viewer"] | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else _require_nonempty(value)


def content_to_dict(content: ReportContentIn) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    for section in content.sections:
        sections.append(
            {
                "id": section.id or "",
                "heading": section.heading,
                "paragraphs": [
                    {
                        "id": paragraph.id or "",
                        "text": paragraph.text,
                        "claimIds": list(dict.fromkeys(paragraph.claimIds)),
                    }
                    for paragraph in section.paragraphs
                ],
            }
        )
    return {"sections": sections}


ALLOWED_TASK_STATUSES = {"blocked", "ready", "running", "approval", "done"}
ALLOWED_STANCES = {"support", "contradict", "neutral"}
ALLOWED_CRITIQUE_SEVERITIES = {"高", "中", "低"}
ALLOWED_CRITIQUE_STATUSES = {"未対応", "対応済", "却下"}
ALLOWED_CANDIDATE_STATUSES = {"候補", "採択", "保留", "却下", "主仮説"}
RESEARCH_TEXT_FIELDS = ("title", "hypothesis", "background", "conditions", "reportNote", "field")
ALLOWED_FIELDS = {"auto", "river", "geo", "concrete", "construction", "general"}
ALLOWED_MEASURE_ROLES = {"独立変数", "従属変数", "関連変数", "統制変数"}
TASK_KEYS = {
    "struct",
    "lit",
    "method",
    "verify",
    "ethics",
    "critic",
    "debate",
    "ideate",
    "evaluate",
    "report",
}
WEIGHT_KEYS = {"evidence", "testability", "burden", "importance", "novelty"}


def _enum_ok(value: Any, allowed: set[str]) -> bool:
    """列挙値を型ごと検証する（list 等の未ハッシュ型で 500 にしない）。"""
    return isinstance(value, str) and value in allowed


RESEARCH_ARRAY_FIELDS = (
    "revisions",
    "tasks",
    "evidence",
    "debate",
    "candidates",
    "decisions",
    "logs",
    "critiques",
    "falsification",
    "ethics",
)


class ResearchDocIn(BaseModel):
    """研究ワークスペース文書の保存入力（楽観ロック付き・形状検証あり）。"""

    expected_version: int = Field(ge=0)
    payload: dict[str, Any]

    @field_validator("payload")
    @classmethod
    def _payload_shape(cls, value: dict[str, Any]) -> dict[str, Any]:
        for key in RESEARCH_TEXT_FIELDS:
            if key in value and not isinstance(value[key], str):
                raise ValueError(f"{key} は文字列で指定してください。")
        if "revision" in value:
            revision = value["revision"]
            if (
                not isinstance(revision, int)
                or isinstance(revision, bool)
                or not 0 <= revision <= 100000
            ):
                raise ValueError("revision は 0 以上 100000 以下の整数で指定してください。")
        if "field" in value and not _enum_ok(value["field"], ALLOWED_FIELDS):
            raise ValueError("field が不正です。")
        if (
            "analysis" in value
            and value["analysis"] is not None
            and not isinstance(value["analysis"], dict)
        ):
            raise ValueError("analysis はオブジェクトで指定してください。")
        analysis = value.get("analysis")
        if analysis is not None:
            if not _enum_ok(analysis.get("field"), ALLOWED_FIELDS):
                raise ValueError("analysis.field が不正です。")
            for key in ("vars", "inferred", "nums", "vague"):
                items = analysis.get(key)
                if items is not None and (
                    not isinstance(items, list) or any(not isinstance(item, str) for item in items)
                ):
                    raise ValueError(f"analysis.{key} は文字列の配列で指定してください。")
            for key in ("iv", "dv", "dir"):
                if analysis.get(key) is not None and not isinstance(analysis[key], str):
                    raise ValueError(f"analysis.{key} は文字列で指定してください。")
            quality = analysis.get("quality")
            if quality is not None:
                if not isinstance(quality, (int, float)) or isinstance(quality, bool):
                    raise ValueError("analysis.quality は数値で指定してください。")
                if not math.isfinite(quality) or not 0 <= quality <= 5:
                    raise ValueError("analysis.quality は 0〜5 の有限値で指定してください。")
            for key in ("hasNum", "hasMech", "hasCond", "hasComp"):
                if analysis.get(key) is not None and not isinstance(analysis[key], bool):
                    raise ValueError(f"analysis.{key} は真偽値で指定してください。")
        constraints = value.get("constraints")
        if constraints is not None:
            if not isinstance(constraints, dict):
                raise ValueError("constraints はオブジェクトで指定してください。")
            if constraints.get("budget") is not None and not _enum_ok(
                constraints["budget"], {"潤沢", "標準", "厳しい"}
            ):
                raise ValueError("constraints.budget が不正です。")
            if constraints.get("period") is not None and not _enum_ok(
                constraints["period"], {"余裕あり", "標準", "短期"}
            ):
                raise ValueError("constraints.period が不正です。")
            if constraints.get("safety") is not None and not isinstance(
                constraints["safety"], bool
            ):
                raise ValueError("constraints.safety は真偽値で指定してください。")
        for key in RESEARCH_ARRAY_FIELDS:
            if key in value and value[key] is not None and not isinstance(value[key], list):
                raise ValueError(f"{key} は配列で指定してください。")
        for task in value.get("tasks") or []:
            if not isinstance(task, dict):
                raise ValueError("tasks の要素はオブジェクトで指定してください。")
            status = task.get("status")
            if status is not None and not _enum_ok(status, ALLOWED_TASK_STATUSES):
                raise ValueError("tasks.status が不正です。")
            if "key" in task and not _enum_ok(task["key"], TASK_KEYS):
                raise ValueError("tasks.key が不正です。")
            progress = task.get("progress")
            if progress is not None:
                if not isinstance(progress, (int, float)) or isinstance(progress, bool):
                    raise ValueError("tasks.progress は数値で指定してください。")
                if not math.isfinite(progress) or not 0 <= progress <= 100:
                    raise ValueError("tasks.progress は 0〜100 の有限値で指定してください。")
            runs = task.get("runs")
            if runs is not None and (
                not isinstance(runs, int) or isinstance(runs, bool) or not 0 <= runs <= 100000
            ):
                raise ValueError("tasks.runs は 0 以上の整数で指定してください。")
        tasks = value.get("tasks")
        if tasks is not None:
            if len(tasks) != len(TASK_KEYS):
                raise ValueError("tasks は 10 件で指定してください。")
            if {task.get("key") for task in tasks} != TASK_KEYS:
                raise ValueError("tasks.key は既定の 10 種類を重複なく指定してください。")
        for evidence in value.get("evidence") or []:
            if not isinstance(evidence, dict):
                raise ValueError("evidence の要素はオブジェクトで指定してください。")
            stance = evidence.get("stance")
            if stance is not None and not _enum_ok(stance, ALLOWED_STANCES):
                raise ValueError("evidence.stance が不正です。")
            if evidence.get("id") is not None and not isinstance(evidence["id"], str):
                raise ValueError("evidence.id は文字列で指定してください。")
            for key in ("reliability", "relevance"):
                metric = evidence.get(key)
                if metric is not None:
                    if not isinstance(metric, (int, float)) or isinstance(metric, bool):
                        raise ValueError(f"evidence.{key} は数値で指定してください。")
                    if not math.isfinite(metric) or not 0 <= metric <= 100:
                        raise ValueError(f"evidence.{key} は 0〜100 の有限値で指定してください。")
            tags = evidence.get("tags")
            if tags is not None and (
                not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags)
            ):
                raise ValueError("evidence.tags は文字列の配列で指定してください。")
        for critique in value.get("critiques") or []:
            if not isinstance(critique, dict):
                raise ValueError("critiques の要素はオブジェクトで指定してください。")
            if critique.get("id") is not None and not isinstance(critique["id"], str):
                raise ValueError("critiques.id は文字列で指定してください。")
            sev = critique.get("sev")
            if sev is not None and not _enum_ok(sev, ALLOWED_CRITIQUE_SEVERITIES):
                raise ValueError("critiques.sev が不正です。")
            status = critique.get("status")
            if status is not None and not _enum_ok(status, ALLOWED_CRITIQUE_STATUSES):
                raise ValueError("critiques.status が不正です。")
        for candidate in value.get("candidates") or []:
            if not isinstance(candidate, dict):
                raise ValueError("candidates の要素はオブジェクトで指定してください。")
            status = candidate.get("status")
            if status is not None and not _enum_ok(status, ALLOWED_CANDIDATE_STATUSES):
                raise ValueError("candidates.status が不正です。")
            for key in ("id", "label", "type", "origin", "text"):
                if candidate.get(key) is not None and not isinstance(candidate[key], str):
                    raise ValueError(f"candidates.{key} は文字列で指定してください。")
            if isinstance(candidate.get("label"), str) and len(candidate["label"]) > 50:
                raise ValueError("candidates.label は 50 文字以内で指定してください。")
            if isinstance(candidate.get("id"), str) and len(candidate["id"]) > 64:
                raise ValueError("candidates.id は 64 文字以内で指定してください。")
            total = candidate.get("total")
            if total is not None:
                if not isinstance(total, (int, float)) or isinstance(total, bool):
                    raise ValueError("candidates.total は数値で指定してください。")
                if not math.isfinite(total) or not 0 <= total <= 100:
                    raise ValueError("candidates.total は 0〜100 の有限値で指定してください。")
            scores = candidate.get("scores")
            if scores is not None:
                if not isinstance(scores, dict):
                    raise ValueError("candidates.scores はオブジェクトで指定してください。")
                for score in scores.values():
                    if not isinstance(score, (int, float)) or isinstance(score, bool):
                        raise ValueError("candidates.scores の値は数値で指定してください。")
                    if not math.isfinite(score) or not 0 <= score <= 100:
                        raise ValueError("candidates.scores は 0〜100 の有限値で指定してください。")
        plan = value.get("plan")
        if plan is not None:
            if not isinstance(plan, dict):
                raise ValueError("plan はオブジェクトで指定してください。")
            for key in ("methods", "measures", "controls"):
                if plan.get(key) is not None and not isinstance(plan[key], list):
                    raise ValueError(f"plan.{key} は配列で指定してください。")
                for item in plan.get(key) or []:
                    if not isinstance(item, dict):
                        raise ValueError(f"plan.{key} の要素はオブジェクトで指定してください。")
            for method in plan.get("methods") or []:
                for key in ("cost", "time", "val"):
                    metric = method.get(key)
                    if metric is not None:
                        if not isinstance(metric, (int, float)) or isinstance(metric, bool):
                            raise ValueError(f"plan.methods.{key} は数値で指定してください。")
                        if not math.isfinite(metric) or not 1 <= metric <= 5:
                            raise ValueError(
                                f"plan.methods.{key} は 1〜5 の有限値で指定してください。"
                            )
            for key in ("measures", "controls"):
                for item in plan.get(key) or []:
                    role = item.get("role")
                    if (
                        key == "measures"
                        and role is not None
                        and not _enum_ok(role, ALLOWED_MEASURE_ROLES)
                    ):
                        raise ValueError("plan.measures.role が不正です。")
        weights = value.get("weights")
        if weights is not None:
            if not isinstance(weights, dict):
                raise ValueError("weights はオブジェクトで指定してください。")
            for key, weight in weights.items():
                if key not in WEIGHT_KEYS:
                    raise ValueError("weights のキーが不正です。")
                if not isinstance(weight, (int, float)) or isinstance(weight, bool):
                    raise ValueError("weights の値は数値で指定してください。")
                if not math.isfinite(weight) or not 0 <= weight <= 50:
                    raise ValueError("weights の値は 0〜50 の有限値で指定してください。")
        return value
