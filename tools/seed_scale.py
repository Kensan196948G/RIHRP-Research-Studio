#!/usr/bin/env python3
"""性能検証用の大規模データを投入する（破壊的。DB 名に "scale" を含む場合のみ）。

    .venv/bin/python tools/seed_scale.py 'postgresql+psycopg://.../rihrp_scale' \
        --sources 200 --claims 1000 --seed-password '***'

本番 DB や開発 DB では実行しない（DB 名ガードで拒否する）。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from urllib.parse import urlparse

parser = argparse.ArgumentParser()
parser.add_argument("database_url")
parser.add_argument("--sources", type=int, default=200)
parser.add_argument("--claims", type=int, default=1000)
parser.add_argument("--seed-password", required=True)
args = parser.parse_args()

db_name = urlparse(args.database_url).path.lstrip("/")
if "scale" not in db_name:
    print(f"BLOCKED: DB 名に scale を含む必要があります（{db_name}）", file=sys.stderr)
    raise SystemExit(2)

os.environ.update(
    RIHRP_ENV="test",
    RIHRP_DATABASE_URL=args.database_url,
    RIHRP_SEED_DEMO="false",
    RIHRP_SEED_PASSWORD=args.seed_password,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from rihrp.db import SessionLocal  # noqa: E402
from rihrp.models import Claim, ClaimEvidence, Project, Report, Source, User  # noqa: E402
from rihrp.security import hash_password  # noqa: E402
from rihrp.services import make_version, sha256_text, verify_claim_row  # noqa: E402

started = time.perf_counter()
with SessionLocal() as db:
    for role, email in [
        ("admin", "admin@scale.local"),
        ("editor", "editor@scale.local"),
        ("reviewer", "reviewer@scale.local"),
        ("viewer", "viewer@scale.local"),
    ]:
        db.merge(
            User(
                email=email,
                name=f"scale {role}",
                role=role,
                password_hash=hash_password(args.seed_password),
            )
        )
    db.flush()
    editor = db.query(User).filter_by(email="editor@scale.local").one()

    project = Project(
        title="性能検証テーマ",
        summary="大規模データでの p95 を測るための検証用テーマ。",
        owner_id=editor.id,
    )
    db.add(project)
    db.flush()

    sources: list[Source] = []
    for index in range(args.sources):
        value = 10000 + index
        body = (
            f"出典 {index} の本文。値は {value} である。"
            "この本文は性能検証のために生成された固定テキストであり、"
            "引用の実在確認と SHA-256 の再計算に使われる。"
        )
        source = Source(
            project_id=project.id,
            title=f"出典 {index}",
            kind="text",
            origin=f"scale:{index}",
            content=body,
            content_sha256=sha256_text(body),
            created_by=editor.id,
        )
        db.add(source)
        sources.append(source)
    db.flush()

    claims: list[Claim] = []
    for index in range(args.claims):
        source = sources[index % len(sources)]
        value = 10000 + (index % len(sources))
        claim = Claim(
            project_id=project.id,
            text=f"出典 {index % len(sources)} の値は {value} である。",
            created_by=editor.id,
        )
        db.add(claim)
        db.flush()
        db.add(
            ClaimEvidence(
                claim_id=claim.id,
                source_id=source.id,
                quote=f"値は {value} である",
                note="性能検証",
            )
        )
        verify_claim_row(db, claim, actor_id=editor.id)
        claims.append(claim)
        if index % 200 == 199:
            db.flush()

    sections = []
    for section_index in range(20):
        paragraphs = []
        for paragraph_index in range(5):
            claim_slice = claims[(section_index * 5 + paragraph_index) * 2 : (section_index * 5 + paragraph_index) * 2 + 2]
            paragraphs.append(
                {
                    "id": f"p-{section_index}-{paragraph_index}",
                    "text": f"性能検証の段落 {section_index}-{paragraph_index}。",
                    "claimIds": [claim.id for claim in claim_slice],
                }
            )
        sections.append({"id": f"s-{section_index}", "heading": f"セクション {section_index}", "paragraphs": paragraphs})

    report = Report(
        project_id=project.id,
        title="性能検証レポート",
        content={"sections": sections},
        created_by=editor.id,
    )
    db.add(report)
    db.flush()
    make_version(db, report, actor_id=editor.id, note="scale")
    db.commit()

    print(
        f"seeded: project={project.id} sources={args.sources} claims={args.claims} "
        f"report={report.id} elapsed={time.perf_counter() - started:.1f}s"
    )
