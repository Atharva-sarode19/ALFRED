"""
Gemini-specific implementation of `LLMProvider`.

This is the ONLY file in the codebase that should import the Gemini SDK.
Everything else -- the agent, the tool registry, the API layer -- talks to
`LLMProvider`, not to Gemini. That isolation is what lets this file be
swapped or updated independently (e.g. when the SDK changes) without
touching agent logic.

Uses Google's official `google-genai` SDK:
    pip install google-genai

Docs: https://ai.google.dev/gemini-api/docs/function-calling
"""

from __future__ import annotations

import logging
from typing import Any

from google.genai import errors as genai_errors
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config.settings import Settings, get_settings
from app.services.llm import (
    GenerationResult,
    LLMAuthenticationError,
    LLMBadRequestError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMUnavailableError,
    Message,
    Role,
    ToolCallRequest,
    ToolDefinition,
)

logger = logging.getLogger("alfred.gemini")
_RETRYABLE_STATUS_CODES = {503, 429}


def _is_retryable_gemini_error(exc: BaseException) -> bool:
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.APIError):
        return getattr(exc, "code", None) in _RETRYABLE_STATUS_CODES
    return False


class GeminiProvider(LLMProvider):
    """
    LLMProvider backed by the Google Gemini API.

    The exact model is never hard-coded here -- it comes from
    `GEMINI_MODEL` via Settings, so operators can point ALFRED at a
    different Gemini model without touching code.
    """

    def __init__(self, settings: Settings | None = None, client: Any = None):
        self._settings = settings or get_settings()
        # Allow dependency injection of a pre-built client for testing.
        self._client = client

    # -- lazy client construction -----------------------------------------
    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover
            raise LLMProviderError(
                "google-genai is not installed. Run `pip install google-genai`."
            ) from exc

        api_key = self._settings.require_gemini_api_key()
        self._client = genai.Client(api_key=api_key)
        return self._client

    # -- public interface ---------------------------------------------
    async def generate(
        self,
        messages: list[Message],
        *,
        system_instruction: str | None = None,
    ) -> GenerationResult:
        return await self._call(messages, tools=None, system_instruction=system_instruction)

    async def generate_with_tools(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        *,
        system_instruction: str | None = None,
    ) -> GenerationResult:
        return await self._call(messages, tools=tools, system_instruction=system_instruction)

    # -- internals --------------------------------------------------------
    async def _call(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None,
        system_instruction: str | None,
    ) -> GenerationResult:
        from google.genai import types

        client = self._get_client()
        model = self._settings.gemini_model

        contents = _to_gemini_contents(messages)

        config_kwargs: dict[str, Any] = {}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if tools:
            config_kwargs["tools"] = [_to_gemini_tool(tools)]

        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        retrying = AsyncRetrying(
            retry=retry_if_exception(_is_retryable_gemini_error),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        try:
            async for attempt in retrying:
                with attempt:
                    response = await client.aio.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config,
                    )
        except genai_errors.ServerError as exc:
            logger.error("Gemini still unavailable after retries: %s", exc)
            raise LLMUnavailableError(
                "The language model is temporarily overloaded and did not "
                "recover after retrying. Please try again shortly."
            ) from exc
        except genai_errors.ClientError as exc:
            status_code = getattr(exc, "code", None)
            if status_code in (401, 403):
                logger.error(
                    "Gemini rejected our credentials (status %s): %s", status_code, exc
                )
                raise LLMAuthenticationError(
                    "The language model rejected our credentials. The "
                    "GEMINI_API_KEY is missing, invalid, or unsupported by "
                    "the API (e.g. a newer 'AQ.'-format key that the REST "
                    "endpoint doesn't accept yet) -- check server logs and "
                    "the key configuration."
                ) from exc
            if status_code == 429:
                logger.error("Gemini rate-limited the request: %s", exc)
                raise LLMRateLimitError(
                    "The language model is rate-limiting requests right now. "
                    "Please wait a moment and try again."
                ) from exc
            logger.error("Gemini rejected the request (status %s): %s", status_code, exc)
            raise LLMBadRequestError(
                "The language model rejected the request itself (e.g. a "
                "malformed prompt or tool schema). Check server logs for "
                "details."
            ) from exc
        except Exception as exc:  # noqa: BLE001 - normalize all provider errors
            logger.exception("Gemini generate_content call failed")
            raise LLMProviderError(f"Gemini API call failed: {exc}") from exc

        return _from_gemini_response(response)


# ---- translation helpers: agent-agnostic <-> Gemini-specific ------------


def _to_gemini_contents(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert normalized Message objects into Gemini `contents` format."""
    contents: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == Role.SYSTEM:
            # System messages are passed separately via system_instruction;
            # skip them here to avoid double-counting.
            continue

        if msg.role == Role.TOOL:
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "function_response": {
                                "name": msg.name,
                                "response": {"result": msg.content},
                            }
                        }
                    ],
                }
            )
            continue

        gemini_role = "model" if msg.role == Role.ASSISTANT else "user"
        parts: list[dict[str, Any]] = []
        if msg.content:
            parts.append({"text": msg.content})
        for call in msg.tool_calls:
            part: dict[str, Any] = {
                "function_call": {"name": call.name, "args": call.arguments}
            }
            if call.thought_signature is not None:
                part["thought_signature"] = call.thought_signature
            parts.append(part)
        if parts:
            contents.append({"role": gemini_role, "parts": parts})
    return contents


def _to_gemini_tool(tools: list[ToolDefinition]):
    from google.genai import types

    declarations = [
        types.FunctionDeclaration(
            name=tool.name,
            description=tool.description,
            parameters=_clean_schema_for_gemini(tool.parameters),
        )
        for tool in tools
    ]
    return types.Tool(function_declarations=declarations)


def _resolve_schema(schema: dict, defs: dict) -> dict:
    """Inline ``$ref``/``$defs`` and strip keys Gemini's Schema type rejects."""
    if "$ref" in schema:
        ref_name = schema["$ref"].rsplit("/", 1)[-1]
        target = defs.get(ref_name, {})
        merged = {**target, **{key: value for key, value in schema.items() if key != "$ref"}}
        return _resolve_schema(merged, defs)

    if "allOf" in schema:
        # Pydantic wraps "$ref + description" in allOf; collapse it.
        merged: dict[str, Any] = {}
        for item in schema["allOf"]:
            merged.update(_resolve_schema(item, defs))
        rest = {key: value for key, value in schema.items() if key != "allOf"}
        merged.update(rest)
        return _resolve_schema(merged, defs)

    if "anyOf" in schema:
        # Optional[X] includes a null branch, which Gemini does not support.
        branches = [branch for branch in schema["anyOf"] if branch.get("type") != "null"]
        resolved = _resolve_schema(branches[0], defs) if branches else {"type": "string"}
        for key, value in schema.items():
            if key != "anyOf":
                resolved.setdefault(key, value)
        return resolved

    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key in ("$defs", "title", "additionalProperties", "$schema"):
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {name: _resolve_schema(prop, defs) for name, prop in value.items()}
        elif key == "items" and isinstance(value, dict):
            out[key] = _resolve_schema(value, defs)
        else:
            out[key] = value
    return out


def _clean_schema_for_gemini(schema: dict) -> dict:
    defs = schema.get("$defs", {})
    cleaned = _resolve_schema(schema, defs)
    cleaned.pop("$defs", None)
    return cleaned


def _from_gemini_response(response: Any) -> GenerationResult:
    """Normalize a Gemini response into a provider-agnostic GenerationResult."""
    text: str | None = None
    tool_calls: list[ToolCallRequest] = []
    finish_reason: str | None = None

    candidates = getattr(response, "candidates", None) or []
    if candidates:
        candidate = candidates[0]
        finish_reason = getattr(candidate, "finish_reason", None)
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        text_chunks: list[str] = []
        for idx, part in enumerate(parts):
            fn = getattr(part, "function_call", None)
            if fn is not None:
                tool_calls.append(
                    ToolCallRequest(
                        id=f"{fn.name}-{idx}",
                        name=fn.name,
                        arguments=dict(fn.args) if fn.args else {},
                        thought_signature=getattr(part, "thought_signature", None),
                    )
                )
            elif getattr(part, "text", None):
                text_chunks.append(part.text)
        if text_chunks:
            text = "".join(text_chunks)

    if text is None and not tool_calls:
        # Fall back to the SDK's convenience accessor if parts parsing
        # yielded nothing (keeps this resilient to minor SDK shape changes).
        text = getattr(response, "text", None)

    return GenerationResult(
        text=text,
        tool_calls=tool_calls,
        finish_reason=str(finish_reason) if finish_reason is not None else None,
        raw=response,
    )