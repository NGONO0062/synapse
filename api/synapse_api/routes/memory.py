"""Mémoire du projet (section 7, écran 7) : six documents validés, leur historique, l'export Excel.

Le PO la consulte ; le testeur et l'administrateur n'y ont pas accès (visibilité v1). Elle ne se
modifie pas par l'API : elle change quand le PO répond à une casquette ou quand une tâche
validée passe en Done.
"""

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from synapse_api import memory
from synapse_api.auth import User, require_any
from synapse_api.db.models import MemoryVersion
from synapse_api.db.session import get_session
from synapse_api.domain.enums import MemoryDocument, Role
from synapse_api.routes.projects import load_project
from synapse_api.schemas import MemoryCardOut, MemoryDocumentOut, MemoryOut, MemoryVersionOut

router = APIRouter(prefix="/projects/{project_id}/memory", tags=["mémoire"])
DB = Annotated[Session, Depends(get_session)]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _version(version: MemoryVersion) -> MemoryVersionOut:
    return MemoryVersionOut(
        version=version.version,
        count=len(version.items),
        summary=version.summary,
        validated_by=version.validated_by,
        validated_at=version.validated_at,
        source_task=version.source_task.code if version.source_task else None,
        commit=version.commit,
    )


def _card(document: MemoryDocument, latest: MemoryVersion | None) -> MemoryCardOut:
    return MemoryCardOut(
        document=document,
        label=memory.LABELS[document],
        file=f"{memory.MEMORY_DIR}/{memory.FILES[document]}",
        count_label=memory.count_label(document, len(latest.items) if latest else 0),
        latest=_version(latest) if latest else None,
    )


@router.get("", response_model=MemoryOut)
def get_memory(project_id: uuid.UUID, user: User, session: DB) -> MemoryOut:
    require_any(user, Role.PO)
    project = load_project(session, project_id)
    documents = [_card(d, v) for d, v in memory.current(session, project.id).items()]
    return MemoryOut(project_id=project.id, project_name=project.name, documents=documents)


@router.get("/scenarios.xlsx", response_class=Response)
def download_scenarios(project_id: uuid.UUID, user: User, session: DB) -> Response:
    """Export Excel des scénarios, dans le modèle du projet (dernière version validée)."""
    require_any(user, Role.PO)
    project = load_project(session, project_id)
    items = memory.items_of(session, project.id, MemoryDocument.SCENARIOS)
    slug = re.sub(r"[^a-z0-9]+", "-", project.name.lower()).strip("-") or "projet"
    return Response(
        memory.scenarios_xlsx(items, project.name),
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="scenarios-{slug}.xlsx"'},
    )


@router.get("/{document}", response_model=MemoryDocumentOut)
def get_document(
    project_id: uuid.UUID,
    document: MemoryDocument,
    user: User,
    session: DB,
    version: Annotated[int | None, Query(ge=1)] = None,
) -> MemoryDocumentOut:
    require_any(user, Role.PO)
    project = load_project(session, project_id)
    versions = memory.history(session, project.id, document)
    shown = versions[0] if versions else None
    if version is not None:
        shown = next((v for v in versions if v.version == version), None)
        if shown is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Version introuvable.")
    card = _card(document, versions[0] if versions else None)
    return MemoryDocumentOut(
        **card.model_dump(),
        version=_version(shown) if shown else None,
        items=list(shown.items) if shown else [],
        history=[_version(v) for v in versions],
    )
