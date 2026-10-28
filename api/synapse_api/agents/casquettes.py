"""Ce qui rend une casquette experte (section 3) : un référentiel versionné, chargé avant
chaque travail, et dont la version est journalisée avec chaque proposition."""

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from synapse_api.domain.enums import Casquette

REFERENTIELS = Path(__file__).parent / "referentiels"

LABELS = {
    Casquette.ORCHESTRATEUR: "Orchestrateur",
    Casquette.BUSINESS_ANALYST: "Business Analyst",
    Casquette.UX_UI_DESIGNER: "UX/UI Designer",
    Casquette.ARCHITECTE: "Architecte",
    Casquette.DEVELOPPEUR: "Développeur",
    Casquette.REVIEWER: "Reviewer de code",
    Casquette.ANALYSTE_TEST: "Analyste de test",
    Casquette.AUTOMATICIEN: "Automaticien",
    Casquette.EXPERT_SECURITE: "Expert sécurité",
    Casquette.DEBOGUEUR: "Débogueur",
    Casquette.REDACTEUR: "Rédacteur technique",
    Casquette.DEVOPS: "DevOps",
}


@dataclass(frozen=True)
class Referentiel:
    casquette: Casquette
    text: str
    # « debogueur@1a2b3c4d » : l'empreinte change dès que le référentiel change.
    version: str


@lru_cache
def referentiel(casquette: Casquette) -> Referentiel:
    name = casquette.value.lower()
    text = (REFERENTIELS / f"{name}.md").read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return Referentiel(casquette, text, f"{name}@{digest}")


def system_prompt(casquette: Casquette) -> str:
    ref = referentiel(casquette)
    return (
        f"Tu portes la casquette « {LABELS[casquette]} » dans Synapse, une équipe d'agents IA qui "
        "conçoit, développe, teste et déploie des applications. L'IA propose, l'humain valide : "
        "tu ne décides jamais à sa place.\n"
        "Réponds en français et tutoie l'humain. Dis ce dont tu n'es pas sûr, ce que tu supposes et ce que "
        "tu n'as pas pu vérifier ; n'invente aucun fait sur le projet. N'écris jamais de secret.\n\n"
        f"Ton référentiel (version {ref.version}) :\n\n{ref.text}"
    )
