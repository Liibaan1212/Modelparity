"""OpenAI-compatible HTTP adapter for ModelParity.

Supports any provider that implements the OpenAI Chat Completions REST API,
including OpenAI itself, Azure OpenAI, Groq, Mistral, Together AI, etc.
"""

from __future__ import annotations

import logging
import os
import warnings
from typing import Any

import httpx

from modelparity.adapters.base import AdapterCapabilities, BaseAdapter
from modelparity.models import NormalizedResponse, RedactionPolicy, ToolCall

logger = logging.getLogger(__name__)

# Default capabilities assumed for any OpenAI-compatible endpoint.
_DEFAULT_CAPABILITIES = ["chat_completions", "finish_reason"]


class OpenAICompatibleAdapter(BaseAdapter):
    """Adapter for any provider implementing the OpenAI Chat Completions API.

    Parameters
    ----------
    base_url:
        The root URL for the API, e.g. ``https://api.openai.com/v1``.
        Must include the version prefix if required by the provider.
    model:
        The model identifier to pass in requests, e.g. ``"gpt-4o"``.
    api_key_env:
        Name of the environment variable that holds the API key.
        The key is **read at send-time** and never stored on the instance.
    capabilities_override:
        If given, replaces the default capability list entirely.
        Pass an empty list to declare no capabilities.
    redaction_policy:
        Controls how sensitive fields appear in :meth:`get_manifest`.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key_env: str,
        capabilities_override: list[str] | None = None,
        redaction_policy: RedactionPolicy = RedactionPolicy.REDACT_ALL,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key_env = api_key_env
        self._redaction_policy = redaction_policy

        cap_list = (
            capabilities_override
            if capabilities_override is not None
            else _DEFAULT_CAPABILITIES
        )
        self._capabilities = AdapterCapabilities(supported=cap_list)

    # ------------------------------------------------------------------
    # BaseAdapter interface
    # ------------------------------------------------------------------

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Advertised capabilities for this adapter instance."""
        return self._capabilities

    async def send(
        self,
        request_spec: dict,
        timeout: float = 30.0,
    ) -> NormalizedResponse:
        """Send *request_spec* to the OpenAI-compatible endpoint.

        Only fields corresponding to declared capabilities are included in
        the outgoing request body. Extra fields are silently dropped (with a
        warning when relevant capabilities are missing).

        Parameters
        ----------
        request_spec:
            Provider-agnostic dict. Recognised keys:
            ``messages``, ``temperature``, ``max_tokens``, ``seed``,
            ``response_format``, ``tools``, ``test_id``.
        timeout:
            Maximum seconds to wait for the HTTP response.

        Returns
        -------
        NormalizedResponse
            On success: parsed response.
            On failure: response with ``error`` and ``error_code`` set.
        """
        test_id: str = request_spec.get("test_id", "")

        # --- Read API key from environment at send-time ---
        api_key = os.environ.get(self._api_key_env, "")
        if not api_key:
            logger.warning(
                "Environment variable %r is not set or is empty. "
                "Requests may be rejected by the provider.",
                self._api_key_env,
            )

        body = self._build_request_body(request_spec)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
        except httpx.TimeoutException:
            return NormalizedResponse(
                test_id=test_id,
                error="Request timed out.",
                error_code="TIMEOUT",
            )
        except httpx.HTTPStatusError as exc:
            # Avoid leaking response body (may contain keys/PII).
            status = exc.response.status_code
            return NormalizedResponse(
                test_id=test_id,
                error=f"HTTP {status} error from provider.",
                error_code="REQUEST_ERROR",
            )
        except httpx.RequestError:
            return NormalizedResponse(
                test_id=test_id,
                error="Network error while contacting provider.",
                error_code="REQUEST_ERROR",
            )

        return self._parse_response(data, test_id)

    def get_manifest(self) -> dict:
        """Return safe, non-secret metadata about this adapter.

        The ``base_url`` is included or redacted according to
        :attr:`redaction_policy`.

        Returns
        -------
        dict
            Keys: ``adapter``, ``model``, ``capabilities``, ``base_url``.
        """
        if self._redaction_policy == RedactionPolicy.SHOW_ALL:
            base_url_display = self._base_url
        elif self._redaction_policy == RedactionPolicy.SHOW_BASE_URL:
            base_url_display = self._base_url
        else:  # REDACT_ALL (default)
            base_url_display = "[REDACTED]"

        return {
            "adapter": "openai_compatible",
            "model": self._model,
            "capabilities": list(self._capabilities.supported),
            "base_url": base_url_display,
            "api_key_env": self._api_key_env,  # env var name only, never the value
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_request_body(self, request_spec: dict) -> dict:
        """Construct the JSON body for the Chat Completions request.

        Only fields backed by a declared capability are included.
        """
        body: dict[str, Any] = {
            "model": self._model,
            "messages": request_spec.get("messages", []),
        }

        if "temperature" in request_spec and request_spec["temperature"] is not None:
            body["temperature"] = request_spec["temperature"]

        if "max_tokens" in request_spec and request_spec["max_tokens"] is not None:
            body["max_tokens"] = request_spec["max_tokens"]

        # --- Capability-gated fields ---

        if "seed" in request_spec and request_spec["seed"] is not None:
            if self._capabilities.supports("seed"):
                body["seed"] = request_spec["seed"]
            else:
                warnings.warn(
                    "request_spec includes 'seed' but this adapter does not "
                    "declare the 'seed' capability. Field omitted.",
                    UserWarning,
                    stacklevel=2,
                )

        if "response_format" in request_spec and request_spec["response_format"] is not None:
            if self._capabilities.supports("json_schema"):
                body["response_format"] = request_spec["response_format"]
            else:
                warnings.warn(
                    "request_spec includes 'response_format' but this adapter "
                    "does not declare the 'json_schema' capability. Field omitted.",
                    UserWarning,
                    stacklevel=2,
                )

        if "tools" in request_spec and request_spec["tools"] is not None:
            if self._capabilities.supports("tool_calls"):
                body["tools"] = request_spec["tools"]
            else:
                warnings.warn(
                    "request_spec includes 'tools' but this adapter does not "
                    "declare the 'tool_calls' capability. Field omitted.",
                    UserWarning,
                    stacklevel=2,
                )

        return body

    def _parse_response(self, data: dict[str, Any], test_id: str) -> NormalizedResponse:
        """Parse a raw Chat Completions JSON body into a NormalizedResponse."""
        choice: dict[str, Any] = {}
        if data.get("choices"):
            choice = data["choices"][0]

        message: dict[str, Any] = choice.get("message", {})
        content: str | None = message.get("content")

        # Parse tool calls if present
        tool_calls: list[ToolCall] = []
        raw_tool_calls: list[dict] = message.get("tool_calls") or []
        for tc in raw_tool_calls:
            fn = tc.get("function", {})
            tool_calls.append(
                ToolCall(
                    id=tc.get("id", ""),
                    name=fn.get("name", ""),
                    arguments=fn.get("arguments", ""),
                )
            )

        # Usage
        usage: dict[str, int] | None = None
        if self._capabilities.supports("usage_tokens") and "usage" in data:
            usage = {k: v for k, v in data["usage"].items() if isinstance(v, int)}

        return NormalizedResponse(
            test_id=test_id,
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason"),
            model=data.get("model"),
            usage=usage,
            raw=data,
        )
