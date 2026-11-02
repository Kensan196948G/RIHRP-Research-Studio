"""入力スキーマ。"""

from __future__ import annotations

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
