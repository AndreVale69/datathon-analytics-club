from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import boto3
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage


_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
_DEFAULT_BEDROCK_MODEL = "anthropic.claude-3-5-haiku-20241022-v1:0"


def _json_instruction(schema: dict[str, Any]) -> str:
    compact_schema = json.dumps(schema, separators=(",", ":"), ensure_ascii=True)
    return (
        "Return valid JSON only. Do not wrap it in Markdown fences.\n"
        f"JSON schema: {compact_schema}"
    )


def _bedrock_client():
    region_name = (
        os.getenv("BEDROCK_AWS_REGION")
        or os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
    )
    access_key_id = os.getenv("BEDROCK_AWS_ACCESS_KEY_ID")
    secret_access_key = os.getenv("BEDROCK_AWS_SECRET_ACCESS_KEY")
    session_token = os.getenv("BEDROCK_AWS_SESSION_TOKEN")

    client_kwargs: dict[str, Any] = {"region_name": region_name}
    if access_key_id and secret_access_key:
        client_kwargs["aws_access_key_id"] = access_key_id
        client_kwargs["aws_secret_access_key"] = secret_access_key
    if session_token:
        client_kwargs["aws_session_token"] = session_token

    return boto3.client("bedrock-runtime", **client_kwargs)


def _parse_json_response(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise TypeError("Expected JSON object response from LLM.")
    return parsed


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
        return "".join(parts)
    return str(content)


def _build_openai_messages(
    *,
    system_prompt: str,
    schema: dict[str, Any],
    few_shot_messages: list[BaseMessage],
    query: str,
) -> list[BaseMessage]:
    return [
        SystemMessage(content=f"{system_prompt}\n\n{_json_instruction(schema)}"),
        *few_shot_messages,
        HumanMessage(content=query),
    ]


def _render_bedrock_prompt(
    *,
    system_prompt: str,
    schema: dict[str, Any],
    few_shot_messages: list[BaseMessage],
    query: str,
) -> str:
    chunks = [system_prompt, "", _json_instruction(schema), ""]
    for message in few_shot_messages:
        role = "User"
        if isinstance(message, AIMessage):
            role = "Assistant"
        elif isinstance(message, SystemMessage):
            role = "System"
        chunks.append(f"{role}: {_message_text(message)}")
    chunks.extend(["User: " + query, "Assistant:"])
    return "\n".join(chunks)


@dataclass(slots=True)
class JsonPromptExtractor:
    system_prompt: str
    schema: dict[str, Any]
    few_shot_messages: list[BaseMessage]
    provider: str
    openai_model: str
    bedrock_model_id: str

    def invoke(self, payload: dict[str, str]) -> dict[str, Any]:
        query = payload["query"]
        if self.provider == "bedrock":
            return self._invoke_bedrock(query)
        if self.provider == "openai":
            return self._invoke_openai(query)
        raise ValueError(f"Unsupported AI provider: {self.provider}")

    def _invoke_openai(self, query: str) -> dict[str, Any]:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model=self.openai_model, temperature=0, seed=42)
        response = llm.invoke(
            _build_openai_messages(
                system_prompt=self.system_prompt,
                schema=self.schema,
                few_shot_messages=self.few_shot_messages,
                query=query,
            )
        )
        return _parse_json_response(_message_text(response))

    def _invoke_bedrock(self, query: str) -> dict[str, Any]:
        client = _bedrock_client()
        response = client.converse(
            modelId=self.bedrock_model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "text": _render_bedrock_prompt(
                                system_prompt=self.system_prompt,
                                schema=self.schema,
                                few_shot_messages=self.few_shot_messages,
                                query=query,
                            )
                        }
                    ],
                }
            ],
            inferenceConfig={"temperature": 0},
        )
        output = response.get("output", {}).get("message", {}).get("content", [])
        text = "".join(item.get("text", "") for item in output if "text" in item)
        if not text:
            raise ValueError("Bedrock returned no text output.")
        return _parse_json_response(text)


@dataclass(slots=True)
class TextPromptGenerator:
    system_prompt: str
    provider: str
    openai_model: str
    bedrock_model_id: str

    def invoke(self, prompt: str) -> str:
        if self.provider == "bedrock":
            return self._invoke_bedrock(prompt)
        if self.provider == "openai":
            return self._invoke_openai(prompt)
        raise ValueError(f"Unsupported AI provider: {self.provider}")

    def _invoke_openai(self, prompt: str) -> str:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model=self.openai_model, temperature=0.2, seed=42)
        response = llm.invoke(
            [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=prompt),
            ]
        )
        return _message_text(response).strip()

    def _invoke_bedrock(self, prompt: str) -> str:
        client = _bedrock_client()
        response = client.converse(
            modelId=self.bedrock_model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "text": f"{self.system_prompt}\n\nUser: {prompt}\nAssistant:"
                        }
                    ],
                }
            ],
            inferenceConfig={"temperature": 0.2},
        )
        output = response.get("output", {}).get("message", {}).get("content", [])
        text = "".join(item.get("text", "") for item in output if "text" in item).strip()
        if not text:
            raise ValueError("Bedrock returned no text output.")
        return text


def build_json_prompt_extractor(
    *,
    system_prompt: str,
    schema: dict[str, Any],
    few_shot_messages: list[BaseMessage] | None = None,
    provider_env_var: str,
    openai_model_env_var: str,
    bedrock_model_env_var: str,
    default_provider: str = "openai",
    default_openai_model: str = _DEFAULT_OPENAI_MODEL,
    default_bedrock_model: str = _DEFAULT_BEDROCK_MODEL,
) -> JsonPromptExtractor:
    provider = os.getenv(provider_env_var, default_provider).strip().lower() or default_provider
    return JsonPromptExtractor(
        system_prompt=system_prompt,
        schema=schema,
        few_shot_messages=list(few_shot_messages or []),
        provider=provider,
        openai_model=os.getenv(openai_model_env_var, default_openai_model),
        bedrock_model_id=os.getenv(bedrock_model_env_var, default_bedrock_model),
    )


def build_text_prompt_generator(
    *,
    system_prompt: str,
    provider_env_var: str,
    openai_model_env_var: str,
    bedrock_model_env_var: str,
    default_provider: str = "bedrock",
    default_openai_model: str = _DEFAULT_OPENAI_MODEL,
    default_bedrock_model: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
) -> TextPromptGenerator:
    provider = os.getenv(provider_env_var, default_provider).strip().lower() or default_provider
    return TextPromptGenerator(
        system_prompt=system_prompt,
        provider=provider,
        openai_model=os.getenv(openai_model_env_var, default_openai_model),
        bedrock_model_id=os.getenv(bedrock_model_env_var, default_bedrock_model),
    )
