"""検証エンジン（決定論）。ADR-0002 に従い LLM を使わない。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*%?")
WHITESPACE_RE = re.compile(r"\s+")

VERIFIED = "verified"
UNVERIFIED = "unverified"
CONTRADICTED = "contradicted"
INSUFFICIENT = "insufficient"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def extract_numbers(text: str) -> list[str]:
    return NUMBER_RE.findall(text)


@dataclass(frozen=True)
class EvidenceInput:
    source_id: str
    title: str
    content: str
    content_sha256: str
    quote: str


def verify_claim(claim_text: str, evidence: list[EvidenceInput]) -> dict:
    """主張を検証し、判定と理由を返す。

    戻り値: {"verdict": str, "reasons": [str], "details": {...}}
    """
    details: dict = {"evidence": [], "numbers": []}
    reasons: list[str] = []

    if not evidence:
        return {"verdict": INSUFFICIENT, "reasons": ["no_evidence"], "details": details}

    quote_checked = False
    quote_missing = False
    tampered = False

    for item in evidence:
        digest_ok = sha256_text(item.content) == item.content_sha256
        quote_found: bool | None = None
        if item.quote:
            quote_checked = True
            quote_found = normalize(item.quote) in normalize(item.content)
            if not quote_found:
                quote_missing = True
        if not digest_ok:
            tampered = True
        details["evidence"].append(
            {
                "source_id": item.source_id,
                "title": item.title,
                "digest_ok": digest_ok,
                "quote_found": quote_found,
            }
        )

    numbers = extract_numbers(claim_text)
    combined = "\n".join(normalize(item.content) for item in evidence)
    missing_numbers: list[str] = []
    for number in numbers:
        # 数字の境界を考慮する（3 が 30、240 が 1,240 に一致しないようにする）。
        pattern = re.compile(r"(?<![\d.,])" + re.escape(number) + r"(?![\d.,])")
        found = pattern.search(combined) is not None
        details["numbers"].append({"value": number, "found": found})
        if not found:
            missing_numbers.append(number)

    if tampered:
        reasons.append("evidence_tampered")
        return {"verdict": CONTRADICTED, "reasons": reasons, "details": details}

    if quote_missing:
        reasons.append("quote_not_found")
        return {"verdict": CONTRADICTED, "reasons": reasons, "details": details}

    if missing_numbers:
        reasons.append("number_not_found")
        details["missing_numbers"] = missing_numbers
        return {"verdict": UNVERIFIED, "reasons": reasons, "details": details}

    if quote_checked:
        reasons.append("quote_verified")
        return {"verdict": VERIFIED, "reasons": reasons, "details": details}

    if numbers:
        reasons.append("number_verified")
        return {"verdict": VERIFIED, "reasons": reasons, "details": details}

    reasons.append("no_anchor")
    return {"verdict": INSUFFICIENT, "reasons": reasons, "details": details}
