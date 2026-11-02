"""テーマ API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from ..audit import write_audit
from ..auth import Principal, get_principal, require_admin, require_editor
from ..db import get_db
from ..models import Project
from ..schemas import ProjectIn, ProjectPatch
from ..services import get_project_or_404, iso, lock_project, project_stats, utcnow

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _project_payload(project: Project, stats: dict) -> dict:
    return {
        "id": project.id,
        "title": project.title,
        "summary": project.summary,
        "status": project.status,
        "owner_id": project.owner_id,
        "created_at": iso(project.created_at),
        "updated_at": iso(project.updated_at),
        "stats": stats,
    }


@router.get("")
def list_projects(
    principal: Principal = Depends(get_principal),
    db: OrmSession = Depends(get_db),
) -> dict:
    projects = list(db.execute(select(Project).order_by(Project.updated_at.desc())).scalars())
    stats = project_stats(db, [project.id for project in projects])
    return {"projects": [_project_payload(p, stats[p.id]) for p in projects]}


@router.post("", status_code=201)
def create_project(
    payload: ProjectIn,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    project = Project(
        title=payload.title.strip(), summary=payload.summary.strip(), owner_id=principal.user_id
    )
    db.add(project)
    db.flush()
    write_audit(
        db,
        actor_id=principal.user_id,
        action="project.created",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        details={"title": project.title},
    )
    db.commit()
    return {"project": _project_payload(project, project_stats(db, [project.id])[project.id])}


@router.get("/{project_id}")
def get_project(
    project_id: str,
    principal: Principal = Depends(get_principal),
    db: OrmSession = Depends(get_db),
) -> dict:
    project = get_project_or_404(db, project_id)
    return {"project": _project_payload(project, project_stats(db, [project.id])[project.id])}


@router.patch("/{project_id}")
def update_project(
    project_id: str,
    payload: ProjectPatch,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    project = get_project_or_404(db, project_id)
    changes: dict = {}
    if payload.title is not None:
        project.title = payload.title.strip()
        changes["title"] = project.title
    if payload.summary is not None:
        project.summary = payload.summary.strip()
        changes["summary"] = project.summary
    if payload.status is not None:
        project.status = payload.status
        changes["status"] = project.status
    if not changes:
        return {"project": _project_payload(project, project_stats(db, [project.id])[project.id])}
    project.updated_at = utcnow()
    write_audit(
        db,
        actor_id=principal.user_id,
        action="project.updated",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        details=changes,
    )
    db.commit()
    return {"project": _project_payload(project, project_stats(db, [project.id])[project.id])}


@router.delete("/{project_id}")
def delete_project(
    project_id: str,
    principal: Principal = Depends(require_admin),
    db: OrmSession = Depends(get_db),
) -> dict:
    project = get_project_or_404(db, project_id)
    project = lock_project(db, project.id)
    write_audit(
        db,
        actor_id=principal.user_id,
        action="project.deleted",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        details={"title": project.title},
    )
    db.delete(project)
    db.commit()
    return {"ok": True}
