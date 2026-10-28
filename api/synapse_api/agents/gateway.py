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


class LiteLLMModel:
    def __init__(self, name: str) -> None:
        settings = get_settings()
        if not settings.litellm_api_key.get_secret_value():
            raise GatewayError(
                "Clé de la passerelle absente : renseigner SYNAPSE_LITELLM_API_KEY dans api/.env."
            )
        self._chat = ChatOpenAI(
            model=name,
            base_url=settings.litellm_url,
            api_key=settings.litellm_api_key,
            timeout=300,
            max_retries=2,
        )

    def structured(self, schema: type[T], *, system: str, prompt: str) -> T:
        # L'appel d'outil est le format structuré que tous les fournisseurs de la passerelle comprennent.
        runnable = self._chat.with_structured_output(schema, method="function_calling")
        answer = runnable.invoke([("system", system), ("human", prompt)])
        if not isinstance(answer, schema):
            raise GatewayError(f"Réponse inattendue du modèle : {type(answer).__name__}.")
        return answer
