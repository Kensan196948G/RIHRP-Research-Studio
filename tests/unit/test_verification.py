"""検証エンジンの単体テスト（DB 不要）。"""

from __future__ import annotations

from rihrp.verify import EvidenceInput, extract_numbers, sha256_text, verify_claim

CONTENT = "導入可能量は 1,240 MW と試算された。2026年度の実証事業は 3 件である。"


def evidence(
    *, quote: str = "", content: str = CONTENT, digest: str | None = None
) -> EvidenceInput:
    return EvidenceInput(
        source_id="s1",
        title="出典",
        content=content,
        content_sha256=digest if digest is not None else sha256_text(content),
        quote=quote,
    )


def test_number_extraction():
    assert extract_numbers("1,240 MW / 2026年度 / 3 件 / 12.5%") == ["1,240", "2026", "3", "12.5%"]


def test_verified_by_quote():
    result = verify_claim(
        "導入可能量は 1,240 MW である。", [evidence(quote="導入可能量は 1,240 MW")]
    )
    assert result["verdict"] == "verified"
    assert result["reasons"] == ["quote_verified"]


def test_unverified_when_number_missing():
    result = verify_claim("導入可能量は 900 MW である。", [evidence(quote="導入可能量は 1,240 MW")])
    assert result["verdict"] == "unverified"
    assert result["reasons"] == ["number_not_found"]
    assert result["details"]["missing_numbers"] == ["900"]


def test_contradicted_when_quote_missing():
    result = verify_claim(
        "導入可能量は 1,240 MW である。", [evidence(quote="この引用は存在しない")]
    )
    assert result["verdict"] == "contradicted"
    assert result["reasons"] == ["quote_not_found"]


def test_contradicted_when_snapshot_tampered():
    tampered = evidence(
        quote="導入可能量は 1,240 MW",
        content=CONTENT + "（改竄）",
        digest=sha256_text(CONTENT),
    )
    result = verify_claim("導入可能量は 1,240 MW である。", [tampered])
    assert result["verdict"] == "contradicted"
    assert result["reasons"] == ["evidence_tampered"]
    assert result["details"]["evidence"][0]["digest_ok"] is False


def test_insufficient_without_evidence():
    result = verify_claim("導入可能量は 1,240 MW である。", [])
    assert result["verdict"] == "insufficient"
    assert result["reasons"] == ["no_evidence"]


def test_insufficient_without_anchor():
    result = verify_claim("導入可能量は大きい。", [evidence()])
    assert result["verdict"] == "insufficient"
    assert result["reasons"] == ["no_anchor"]


def test_verified_by_numbers_only():
    result = verify_claim("実証事業は 3 件である。", [evidence()])
    assert result["verdict"] == "verified"
    assert result["reasons"] == ["number_verified"]


def test_number_boundaries_are_not_substrings():
    content = "実証事業は 30 件である。導入可能量は 1,240 MW である。"
    source = evidence(content=content)

    assert verify_claim("実証事業は 3 件である。", [source])["verdict"] == "unverified"
    assert verify_claim("導入可能量は 240 MW である。", [source])["verdict"] == "unverified"
    assert verify_claim("導入可能量は 1 MW である。", [source])["verdict"] == "unverified"
    assert verify_claim("実証事業は 30 件である。", [source])["verdict"] == "verified"
    assert verify_claim("導入可能量は 1,240 MW である。", [source])["verdict"] == "verified"
