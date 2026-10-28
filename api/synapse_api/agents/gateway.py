"""Passerelle unique vers les modèles IA (LiteLLM, section 12).

Changer de fournisseur ne touche pas aux casquettes : elles demandent un modèle par son nom
(claude-sonnet, gpt…) et une réponse structurée. La clé de la passerelle reste ici.
"""

from collections.abc import Callable
from typing import Protocol, TypeVar

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from synapse_api.config import get_settings

T = TypeVar("T", bound=BaseModel)


class GatewayError(Exception):
    pass


class Model(Protocol):
    def structured(self, schema: type[T], *, system: str, prompt: str) -> T: ...


ModelFactory = Callable[[str], Model]


# Formats de réponse structurée : l'appel d'outil, puis le schéma JSON imposé à la génération
# (que les petits modèles locaux respectent mieux). Le format qui a marché est retenu par modèle.
METHODS = ("function_calling", "json_schema")
_preferred: dict[str, str] = {}


class LiteLLMModel:
    def __init__(self, name: str) -> None:
        settings = get_settings()
        if not settings.litellm_api_key.get_secret_value():
            raise GatewayError(
                "Clé de la passerelle absente : renseigner SYNAPSE_LITELLM_API_KEY dans api/.env."
            )
        self.name = name
        self._chat = ChatOpenAI(
            model=name,
            base_url=settings.litellm_url,
            api_key=settings.litellm_api_key,
            timeout=900,  # un modèle local sans carte graphique est lent
            max_retries=2,
        )

    def structured(self, schema: type[T], *, system: str, prompt: str) -> T:
        methods = sorted(METHODS, key=lambda method: method != _preferred.get(self.name))
        for method in methods:
            runnable = self._chat.with_structured_output(schema, method=method)
            answer = runnable.invoke([("system", system), ("human", prompt)])
            if isinstance(answer, schema):
                _preferred[self.name] = method
                return answer
        raise GatewayError(f"Le modèle {self.name} n'a pas rendu de réponse structurée.")
