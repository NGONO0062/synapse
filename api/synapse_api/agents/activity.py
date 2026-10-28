"""Activité des casquettes, montrée en direct dans l'interface (indicateur de travail).

Chaque écriture est commitée tout de suite, dans sa propre session : l'humain voit qui
travaille et sur quoi, ou pourquoi rien n'avance (modèle injoignable, clé absente…).
"""

import uuid
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from synapse_api.db.models import TaskActivity, utcnow
from synapse_api.domain.enums import Casquette

QUEUED = "attend son tour"


def report(sessions: sessionmaker[Session], task_id: uuid.UUID, casquette: Casquette, step: str) -> None:
    """La casquette commence une étape ; un échec précédent est effacé."""
    with sessions() as session:
        activity = session.get(TaskActivity, task_id)
        if activity is None:
            session.add(TaskActivity(task_id=task_id, casquette=casquette.value, step=step))
        else:
            activity.casquette, activity.step = casquette.value, step
            activity.error = activity.retry_at = None
            activity.updated_at = utcnow()
        session.commit()


def queue(sessions: sessionmaker[Session], task_id: uuid.UUID, casquette: Casquette) -> None:
    """Travail dû, pas encore commencé (une seule tâche avance à la fois)."""
    with sessions() as session:
        if session.get(TaskActivity, task_id) is None:
            session.add(TaskActivity(task_id=task_id, casquette=casquette.value, step=QUEUED))
            session.commit()


def fail(sessions: sessionmaker[Session], task_id: uuid.UUID, error: str, retry_at: datetime) -> None:
    with sessions() as session:
        activity = session.get(TaskActivity, task_id)
        if activity is not None:
            activity.error, activity.retry_at = error[:1000], retry_at
            session.commit()


def clear(sessions: sessionmaker[Session], task_id: uuid.UUID | None = None) -> None:
    """Travail terminé (ou, sans tâche, démarrage du worker : rien n'est en cours)."""
    with sessions() as session:
        query = delete(TaskActivity)
        if task_id is not None:
            query = query.where(TaskActivity.task_id == task_id)
        session.execute(query)
        session.commit()
