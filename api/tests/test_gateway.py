import pytest
from langchain_core.messages import AIMessage

from synapse_api.agents import gateway
from synapse_api.agents.gateway import GatewayError, LiteLLMModel, Usage, parse_catalog
from synapse_api.agents.jobs import Review


class FakeChat:
    """Modèle factice : répond seulement dans les formats structurés listés."""

    def __init__(self, *supported: str) -> None:
        self.supported = supported
        self.calls: list[str] = []

    def with_structured_output(self, schema, *, method: str, include_raw: bool = False):
        chat = self

        class Runnable:
            def invoke(self, messages):
                chat.calls.append(method)
                parsed = schema(approved=True) if method in chat.supported else None
                tokens = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
                raw = AIMessage("", usage_metadata=tokens)
                return {"raw": raw, "parsed": parsed, "parsing_error": None}

        return Runnable()


def model(name: str, chat: FakeChat) -> LiteLLMModel:
    m = LiteLLMModel.__new__(LiteLLMModel)
    m.name, m._chat, m.last_usage = name, chat, Usage()
    return m


@pytest.fixture(autouse=True)
def fresh_preferences(monkeypatch):
    monkeypatch.setattr(gateway, "_preferred", {})


def test_model_answering_in_free_text_falls_back_to_json_schema():
    chat = FakeChat("json_schema")
    local = model("local", chat)
    assert local.structured(Review, system="", prompt="").approved
    assert chat.calls == ["function_calling", "json_schema"]
    # Le format qui a marché est retenu : un seul appel ensuite.
    local.structured(Review, system="", prompt="")
    assert chat.calls[2:] == ["json_schema"]


def test_tool_calling_is_tried_first():
    chat = FakeChat("function_calling", "json_schema")
    model("claude-sonnet", chat).structured(Review, system="", prompt="")
    assert chat.calls == ["function_calling"]


def test_no_structured_answer_is_an_error():
    with pytest.raises(GatewayError):
        model("local", FakeChat()).structured(Review, system="", prompt="")


def test_a_refused_format_is_counted_in_the_usage():
    local = model("local", FakeChat("json_schema"))
    local.structured(Review, system="", prompt="")
    assert local.last_usage == Usage(200, 40)  # deux essais payés
    local.structured(Review, system="", prompt="")
    assert local.last_usage == Usage(100, 20)  # chaque appel repart de zéro


def test_catalog_gives_the_served_model_and_the_cost_of_a_call():
    catalog = parse_catalog(
        {
            "data": [
                {
                    "model_name": "claude-sonnet",
                    "litellm_params": {"model": "anthropic/claude-sonnet-5-5"},
                    "model_info": {"input_cost_per_token": 3e-06, "output_cost_per_token": 1.5e-05},
                },
                {"model_name": "local", "litellm_params": {"model": "ollama_chat/qwen2.5-coder:3b"}},
            ]
        }
    )
    assert catalog["claude-sonnet"].served_model == "anthropic/claude-sonnet-5-5"
    assert catalog["claude-sonnet"].cost(Usage(1000, 100)) == pytest.approx(0.0045)
    assert catalog["local"].cost(Usage(1000, 100)) is None  # prix inconnu, pas zéro
