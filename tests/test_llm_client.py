import os

from langchain_core.messages import AIMessage, HumanMessage

from app.participant.llm_client import build_json_prompt_extractor


class _FakeOpenAIResponse:
    content = '```json\n{"hard":{},"soft":{}}\n```'


class _FakeOpenAIModel:
    last_messages = None

    def __init__(self, *, model: str, temperature: int, seed: int) -> None:
        self.model = model
        self.temperature = temperature
        self.seed = seed

    def invoke(self, messages):
        _FakeOpenAIModel.last_messages = messages
        return _FakeOpenAIResponse()


class _FakeBedrockClient:
    def __init__(self) -> None:
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "output": {
                "message": {
                    "content": [
                        {"text": '{"hard":{"city":["Zurich"]},"soft":{}}'},
                    ]
                }
            }
        }


def test_json_prompt_extractor_uses_openai_by_default(monkeypatch) -> None:
    monkeypatch.delenv("TEST_PROVIDER", raising=False)
    monkeypatch.setattr("langchain_openai.ChatOpenAI", _FakeOpenAIModel)

    extractor = build_json_prompt_extractor(
        system_prompt="System prompt",
        schema={"type": "object"},
        few_shot_messages=[HumanMessage(content="example"), AIMessage(content='{"ok":true}')],
        provider_env_var="TEST_PROVIDER",
        openai_model_env_var="TEST_OPENAI_MODEL",
        bedrock_model_env_var="TEST_BEDROCK_MODEL_ID",
    )

    result = extractor.invoke({"query": "find me a flat"})

    assert extractor.provider == "openai"
    assert result == {"hard": {}, "soft": {}}
    assert _FakeOpenAIModel.last_messages[0].content.startswith("System prompt")
    assert _FakeOpenAIModel.last_messages[-1].content == "find me a flat"


def test_json_prompt_extractor_uses_bedrock_when_requested(monkeypatch) -> None:
    fake_client = _FakeBedrockClient()
    monkeypatch.setenv("TEST_PROVIDER", "bedrock")
    monkeypatch.setenv("BEDROCK_AWS_REGION", "us-west-2")
    monkeypatch.setenv("BEDROCK_AWS_ACCESS_KEY_ID", "bedrock-key")
    monkeypatch.setenv("BEDROCK_AWS_SECRET_ACCESS_KEY", "bedrock-secret")
    monkeypatch.setenv("BEDROCK_AWS_SESSION_TOKEN", "bedrock-session")
    monkeypatch.setenv("TEST_BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")

    seen = {}

    def fake_boto3_client(*args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return fake_client

    monkeypatch.setattr("app.participant.llm_client.boto3.client", fake_boto3_client)

    extractor = build_json_prompt_extractor(
        system_prompt="System prompt",
        schema={"type": "object"},
        few_shot_messages=[HumanMessage(content="example"), AIMessage(content='{"ok":true}')],
        provider_env_var="TEST_PROVIDER",
        openai_model_env_var="TEST_OPENAI_MODEL",
        bedrock_model_env_var="TEST_BEDROCK_MODEL_ID",
    )
    result = extractor.invoke({"query": "find me a flat"})

    assert extractor.provider == "bedrock"
    assert result == {"hard": {"city": ["Zurich"]}, "soft": {}}
    assert fake_client.calls
    prompt = fake_client.calls[0]["messages"][0]["content"][0]["text"]
    assert "System prompt" in prompt
    assert "User: find me a flat" in prompt
    assert fake_client.calls[0]["modelId"]
    assert seen["args"] == ("bedrock-runtime",)
    assert seen["kwargs"]["region_name"] == "us-west-2"
    assert seen["kwargs"]["aws_access_key_id"] == "bedrock-key"
    assert seen["kwargs"]["aws_secret_access_key"] == "bedrock-secret"
    assert seen["kwargs"]["aws_session_token"] == "bedrock-session"
