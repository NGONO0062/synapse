"""Vocabulaire du domaine Synapse (voir CLAUDE.md, section Domaine)."""

from enum import StrEnum


class Role(StrEnum):
    PO = "PO"
    TESTEUR = "TESTEUR"
    ADMIN = "ADMIN"


class TaskType(StrEnum):
    FEATURE = "FEATURE"
    BUGFIX = "BUGFIX"
    DOC = "DOC"

    @property
    def prefix(self) -> str:
        return {TaskType.FEATURE: "FEAT", TaskType.BUGFIX: "BUG", TaskType.DOC: "DOC"}[self]


class TaskStatus(StrEnum):
    """Ordre de déclaration = ordre d'affichage. Aucun autre statut n'est autorisé."""

    BACKLOG = "BACKLOG"
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    DONE = "DONE"


class Casquette(StrEnum):
    ORCHESTRATEUR = "ORCHESTRATEUR"
    BUSINESS_ANALYST = "BUSINESS_ANALYST"
    UX_UI_DESIGNER = "UX_UI_DESIGNER"
    ARCHITECTE = "ARCHITECTE"
    DEVELOPPEUR = "DEVELOPPEUR"
    REVIEWER = "REVIEWER"
    ANALYSTE_TEST = "ANALYSTE_TEST"
    AUTOMATICIEN = "AUTOMATICIEN"
    EXPERT_SECURITE = "EXPERT_SECURITE"
    DEBOGUEUR = "DEBOGUEUR"
    REDACTEUR = "REDACTEUR"
    DEVOPS = "DEVOPS"


class MessageKind(StrEnum):
    MESSAGE = "MESSAGE"  # texte libre (humain ou casquette)
    PLAN = "PLAN"  # plan proposé, à valider avant exécution
    RESULT = "RESULT"  # livrable proposé, à valider en Review
    QUESTION = "QUESTION"  # question d'un agent, la tâche attend une réponse


# Modèles exposés par la passerelle (infra/litellm/config.yaml).
AI_MODELS: tuple[str, ...] = ("claude-sonnet", "claude-opus", "gpt", "gemini", "mistral")
DEFAULT_AI_MODEL = "claude-sonnet"


class Environment(StrEnum):
    STAGING = "STAGING"
    PREPROD = "PREPROD"
    PROD = "PROD"


class ScenarioPlatformStatus(StrEnum):
    NOT_STARTED = "Not started"
    PASSED = "Passed"
    FAILED = "Failed"


# Colonnes du modèle Excel des scénarios, dans l'ordre imposé.
SCENARIO_COLUMNS: tuple[str, ...] = (
    "Module",
    "Scénario",
    "Préconditions",
    "Étapes",
    "Résultat attendu",
    "Chrome",
    "Firefox",
    "iOS",
    "Android",
)
