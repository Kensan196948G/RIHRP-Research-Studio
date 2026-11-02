"""監査ログ。業務 Tx 内で追記し、ここでは commit しない（ADR-0005）。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AuditEvent
from .request_context import request_id_var


def write_audit(
    db: Session,
    *,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str = "",
    project_id: str | None = None,
    details: dict | None = None,
    request_id: str = "",
) -> AuditEvent:
    event = AuditEvent(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=(entity_id or "")[:36],
        project_id=project_id,
        details=details or {},
        request_id=(request_id or request_id_var.get())[:36],
    )
    db.add(event)
    return event
