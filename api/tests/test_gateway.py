import pytest

from synapse_api.agents import gateway
from synapse_api.agents.gateway import GatewayError, LiteLLMModel
from synapse_api.agents.jobs import Review


class FakeChat:
    """Modèle factice : répond seulement dans les formats structurés listés."""

    def __init__(self, *supported: str) -> None:
        self.supported = supported
        self.calls: list[str] = []

    def with_structured_output(self, schema, *, method: str):
        chat = self

        class Runnable:
            def invoke(self, messages):
                chat.calls.append(method)
                return schema(approved=True) if method in chat.supported else None

        return Runnable()


def model(name: str, chat: FakeChat) -> LiteLLMModel:
    m = LiteLLMModel.__new__(LiteLLMModel)
    m.name, m._chat = name, chat
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
