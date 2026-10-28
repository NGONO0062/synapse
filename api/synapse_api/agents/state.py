"""État des graphes de l'orchestrateur et dépendances injectées dans leurs nœuds."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from sqlalchemy.orm import Session, sessionmaker

from synapse_api.agents.gateway import ModelFactory
from synapse_api.agents.sandbox import DockerSandbox, Sandbox
from synapse_api.config import get_settings


class WorkState(TypedDict, total=False):
    # Travail en cours (voir jobs.Assignment)
    task_id: str
    code: str
    job: str
    version: int
    task_type: str
    ai_model: str
    brief: str
    feedback: list[str]  # corrections à reprendre, ou avertissements si la limite est atteinte
    outcome: str  # published, obsolete, question, plan_change ou escalated
    # Rédaction (reformulation, plan)
    draft: dict[str, Any]
    drafts: int
    # Exécution
    project_id: str
    branch: str
    reproduced: bool
    attempts: int
    message: str
    open_points: list[str]  # remarques de relecture non résolues, montrées au PO
    qa: str | None  # commande de test passée au vert


@dataclass(frozen=True)
class Deps:
    sessions: sessionmaker[Session]
    model: ModelFactory
    sandbox: Sandbox = field(default_factory=DockerSandbox)
    git_dir: Path = field(default_factory=lambda: get_settings().git_dir)
    sandbox_image: str = field(default_factory=lambda: get_settings().sandbox_image)
