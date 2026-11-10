"""Passerelle unique vers les modèles IA (LiteLLM, section 12).

Changer de fournisseur ne touche pas aux casquettes : elles demandent un modèle par son nom
(claude-sonnet, gpt…) et une réponse structurée. La clé de la passerelle reste ici.

La passerelle dit aussi ce que coûte un appel : chaque réponse porte ses jetons, et son
catalogue (/model/info) donne le modèle réel derrière chaque nom et son prix par jeton.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

import httpx
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from synapse_api.config import get_settings

T = TypeVar("T", bound=BaseModel)
log = logging.getLogger("synapse.passerelle")


class GatewayError(Exception):
    pass


@dataclass(frozen=True)
class Usage:
    """Jetons consommés par un appel (essais de format compris)."""

    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens)


class Model(Protocol):
    def structured(self, schema: type[T], *, system: str, prompt: str) -> T: ...


ModelFactory = Callable[[str], Model]


def usage_of(model: Model) -> Usage:
    """Jetons du dernier appel ; un modèle qui ne les compte pas (tests) vaut zéro."""
    return getattr(model, "last_usage", None) or Usage()


# Formats de réponse structurée : l'appel d'outil, puis le schéma JSON imposé à la génération
# (que les petits modèles locaux respectent mieux). Le format qui a marché est retenu par modèle.
METHODS = ("function_calling", "json_schema")
_preferred: dict[str, str] = {}


def _tokens(raw) -> Usage:
    meta = getattr(raw, "usage_metadata", None) or {}
    return Usage(int(meta.get("input_tokens") or 0), int(meta.get("output_tokens") or 0))


class LiteLLMModel:
    def __init__(self, name: str) -> None:
        settings = get_settings()
        if not settings.litellm_api_key.get_secret_value():
            raise GatewayError(
                "Clé de la passerelle absente : renseigner SYNAPSE_LITELLM_API_KEY dans api/.env."
            )
        self.name = name
        self.last_usage = Usage()
        self._chat = ChatOpenAI(
            model=name,
            base_url=settings.litellm_url,
            api_key=settings.litellm_api_key,
            timeout=900,  # un modèle local sans carte graphique est lent
            max_retries=2,
        )

    def structured(self, schema: type[T], *, system: str, prompt: str) -> T:
        self.last_usage = Usage()
        methods = sorted(METHODS, key=lambda method: method != _preferred.get(self.name))
        for method in methods:
            runnable = self._chat.with_structured_output(schema, method=method, include_raw=True)
            answer = runnable.invoke([("system", system), ("human", prompt)])
            # Un essai dans un format refusé est payé quand même.
            self.last_usage += _tokens(answer.get("raw"))
            parsed = answer.get("parsed")
            if isinstance(parsed, schema):
                _preferred[self.name] = method
                return parsed
        raise GatewayError(f"Le modèle {self.name} n'a pas rendu de réponse structurée.")


# Catalogue de la passerelle.


@dataclass(frozen=True)
class ModelInfo:
    name: str  # nom dans la passerelle
    served_model: str  # modèle réel, ex. anthropic/claude-sonnet-5-5
    input_cost: float | None  # dollars par jeton ; inconnu si la passerelle ne le donne pas
    output_cost: float | None

    def cost(self, usage: Usage) -> float | None:
        if self.input_cost is None or self.output_cost is None:
            return None
        return usage.input_tokens * self.input_cost + usage.output_tokens * self.output_cost


def parse_catalog(payload: dict) -> dict[str, ModelInfo]:
    catalog = {}
    for entry in payload.get("data", []):
        name = entry.get("model_name")
        if not name:
            continue
        params = entry.get("litellm_params") or {}
        info = entry.get("model_info") or {}
        catalog[name] = ModelInfo(
            name=name,
            served_model=params.get("model") or name,
            input_cost=info.get("input_cost_per_token"),
            output_cost=info.get("output_cost_per_token"),
        )
    return catalog


Catalog = Callable[[], dict[str, ModelInfo] | None]
_catalog_cache: tuple[float, dict[str, ModelInfo]] | None = None


def gateway_catalog() -> dict[str, ModelInfo] | None:
    """Catalogue de la passerelle, gardé quelques minutes ; None si elle ne répond pas."""
    global _catalog_cache
    settings = get_settings()
    if _catalog_cache and time.monotonic() - _catalog_cache[0] < settings.model_catalog_ttl:
        return _catalog_cache[1]
    try:
        response = httpx.get(
            f"{settings.litellm_url.rstrip('/')}/model/info",
            headers={"Authorization": f"Bearer {settings.litellm_api_key.get_secret_value()}"},
            timeout=10,
        )
        response.raise_for_status()
        catalog = parse_catalog(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Catalogue de la passerelle illisible : %s", exc)
        return _catalog_cache[1] if _catalog_cache else None
    _catalog_cache = (time.monotonic(), catalog)
    return catalog
