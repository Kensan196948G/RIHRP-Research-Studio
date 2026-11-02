"""開発・テスト用の初期データ。本番では実行しない。"""

from __future__ import annotations

import logging
import os

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .models import Claim, ClaimEvidence, Project, Report, Source, User
from .security import hash_password
from .services import make_version, sha256_text, verify_claim_row

logger = logging.getLogger("rihrp.seed")

DEMO_PASSWORD_ENV = "RIHRP_SEED_PASSWORD"  # noqa: S105 - env var name, not a secret

DEMO_USERS = [
    ("admin@rihrp.local", "管理者", "admin"),
    ("editor@rihrp.local", "調査 太郎", "editor"),
    ("reviewer@rihrp.local", "審査 花子", "reviewer"),
    ("viewer@rihrp.local", "閲覧 次郎", "viewer"),
]


def seed_users(db: OrmSession) -> dict[str, User]:
    password = os.environ.get(DEMO_PASSWORD_ENV)
    if not password:
        logger.warning("%s が未設定のためデモ利用者を投入しません", DEMO_PASSWORD_ENV)
        return {}
    created: dict[str, User] = {}
    for email, name, role in DEMO_USERS:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            user = User(email=email, name=name, role=role, password_hash=hash_password(password))
            db.add(user)
        created[role] = user
    db.commit()
    return created


def seed_demo_workspace(db: OrmSession, editor: User) -> None:
    existing = db.execute(select(Project).limit(1)).scalar_one_or_none()
    if existing is not None:
        return

    project = Project(
        title="海洋再生可能エネルギーの導入可能性",
        summary="沿岸部における洋上風力・波力の導入可能量と系統制約を、一次資料と技術レポートから評価する。",
        owner_id=editor.id,
    )
    db.add(project)
    db.flush()

    source_a_text = (
        "海洋再生可能エネルギー導入調査（一次資料抜粋）\n"
        "国内の沿岸部における導入可能量は 1,240 MW と試算された。"
        "2026年度の実証事業は 3 件を予定しており、うち 2 件は浮体式である。"
        "事業化には地元漁協との合意形成が不可欠とされている。"
    )
    source_b_text = (
        "地域送電網の制約に関する技術レポート\n"
        "既存の連系可能量は最大 480 MW にとどまる。"
        "系統増強には 5 年程度を要し、その間の新規接続は制限される見込みである。"
        "一方、需要側の調整力活用により 120 MW 程度の追加余地がある。"
    )
    sources = []
    for title, kind, origin, body in [
        (
            "海洋再生可能エネルギー導入調査",
            "url",
            "https://example.org/ocean-energy-survey",
            source_a_text,
        ),
        ("地域送電網の制約に関する技術レポート", "doi", "10.0000/example.grid.2026", source_b_text),
    ]:
        source = Source(
            project_id=project.id,
            title=title,
            kind=kind,
            origin=origin,
            content=body,
            content_sha256=sha256_text(body),
            created_by=editor.id,
        )
        db.add(source)
        sources.append(source)
    db.flush()

    claims_spec = [
        (
            "国内の沿岸部における導入可能量は 1,240 MW と試算されている。",
            [(sources[0], "導入可能量は 1,240 MW と試算された")],
        ),
        (
            "系統連系の制約により、実際に受け入れられるのは最大 900 MW である。",
            [(sources[1], "既存の連系可能量は最大 480 MW にとどまる")],
        ),
        (
            "2026年度の実証事業は 3 件を予定している。",
            [(sources[0], "2026年度の実証事業は 3 件を予定しており")],
        ),
        (
            "地元漁協との合意形成が事業化の主要な論点である。",
            [],
        ),
    ]
    claims: list[Claim] = []
    for text, evidences in claims_spec:
        claim = Claim(project_id=project.id, text=text, created_by=editor.id)
        db.add(claim)
        db.flush()
        for source, quote in evidences:
            db.add(
                ClaimEvidence(
                    claim_id=claim.id,
                    source_id=source.id,
                    quote=quote,
                    note="デモ用の紐付け",
                )
            )
        claims.append(claim)
    db.flush()

    for claim in claims:
        verify_claim_row(db, claim, actor_id=editor.id)

    report = Report(
        project_id=project.id,
        title="海洋再生可能エネルギー導入の論点整理",
        content={
            "sections": [
                {
                    "id": "sec-1",
                    "heading": "1. 導入可能量",
                    "paragraphs": [
                        {
                            "id": "p-1",
                            "text": "沿岸部の導入可能量は 1,240 MW と試算されている。",
                            "claimIds": [claims[0].id],
                        }
                    ],
                },
                {
                    "id": "sec-2",
                    "heading": "2. 系統制約と実証",
                    "paragraphs": [
                        {
                            "id": "p-2",
                            "text": (
                                "系統連系の制約により、"
                                "受け入れ可能量は導入可能量を下回る可能性がある。"
                            ),
                            "claimIds": [claims[1].id],
                        },
                        {
                            "id": "p-3",
                            "text": "2026年度には 3 件の実証事業が予定されている。",
                            "claimIds": [claims[2].id],
                        },
                    ],
                },
            ]
        },
        created_by=editor.id,
    )
    db.add(report)
    db.flush()
    make_version(db, report, actor_id=editor.id, note="initial")
    db.commit()
    logger.info("seeded demo workspace project=%s", project.id)


def seed_all(db: OrmSession) -> None:
    users = seed_users(db)
    if "editor" not in users:
        return
    seed_demo_workspace(db, users["editor"])
