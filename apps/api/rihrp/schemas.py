"""入力スキーマ。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

MAX_CONTENT_BYTES = 1024 * 1024


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class ProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=5000)


class ProjectPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=5000)
    status: Literal["active", "archived"] | None = None


class SourceIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    kind: Literal["url", "doi", "text"] = "text"
    origin: str = Field(default="", max_length=1000)
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def _content_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_CONTENT_BYTES:
            raise ValueError("本文は 1 MiB 以下にしてください。")
        return value


class ClaimIn(BaseModel):
    text: str = Field(min_length=10, max_length=2000)


class ClaimPatch(BaseModel):
    text: str = Field(min_length=10, max_length=2000)


class EvidenceIn(BaseModel):
    source_id: str = Field(min_length=1, max_length=36)
    quote: str = Field(default="", max_length=500)
    note: str = Field(default="", max_length=1000)


class ReportIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)


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


class ReviewIn(BaseModel):
    decision: Literal["approved", "changes_requested"]
    comment: str = Field(default="", max_length=5000)


class UserIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    name: str = Field(min_length=1, max_length=120)
    role: Literal["admin", "editor", "reviewer", "viewer"]
    password: str = Field(min_length=12, max_length=200)


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Literal["admin", "editor", "reviewer", "viewer"] | None = None
    is_active: bool | None = None


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
