"""Adapter package for ModelParity.

Provides :func:`get_adapter` factory and re-exports the adapter classes.
"""

from __future__ import annotations

from typing import Any

from modelparity.adapters.base import (
    AdapterCapabilities,
    BaseAdapter,
    SUPPORTED_CAPABILITIES,
)
from modelparity.adapters.openai_compatible import OpenAICompatibleAdapter
from modelparity.adapters.recorded import RecordedAdapter
from modelparity.models import RedactionPolicy


def get_adapter(config: dict[str, Any]) -> BaseAdapter:
    """Factory that creates the appropriate adapter from a config dict.

    Parameters
    ----------
    config:
        Adapter configuration dict. Required key: ``type``.

        ``type = "openai_compatible"``
            Additional required keys: ``base_url``, ``model``, ``api_key_env``.
            Optional keys: ``capabilities``, ``redaction_policy``.

        ``type = "recorded"``
            Additional required key: ``fixtures_dir``.

    Returns
    -------
    BaseAdapter
        Configured adapter instance.

    Raises
    ------
    ValueError
        If ``type`` is missing or unrecognised, or if required keys are absent.

    Examples
    --------
    .. code-block:: python

        adapter = get_adapter({
            "type": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o",
            "api_key_env": "OPENAI_API_KEY",
            "capabilities": ["chat_completions", "finish_reason", "seed"],
        })

        recorded = get_adapter({
            "type": "recorded",
            "fixtures_dir": "tests/fixtures",
        })
    """
    adapter_type = config.get("adapter") or config.get("type")
    if not adapter_type:
        raise ValueError(
            "Adapter config must contain an 'adapter' or 'type' key. "
            f"Supported types: 'openai_compatible', 'recorded'."
        )

    if adapter_type == "openai_compatible":
        _require_keys(config, ["base_url"], adapter_type)

        capabilities = config.get("capabilities")  # None means use default
        redaction_str = config.get("redaction_policy", "redact_all")
        try:
            redaction = RedactionPolicy(redaction_str)
        except ValueError:
            valid = [p.value for p in RedactionPolicy]
            raise ValueError(
                f"Invalid redaction_policy {redaction_str!r}. Valid options: {valid}"
            )

        return OpenAICompatibleAdapter(
            base_url=config["base_url"],
            model=config.get("model") or "",
            api_key_env=config.get("api_key_env") or "",
            capabilities_override=capabilities,
            redaction_policy=redaction,
        )

    if adapter_type == "recorded":
        _require_keys(config, ["fixtures_dir"], adapter_type)
        from pathlib import Path

        return RecordedAdapter(fixtures_dir=Path(config["fixtures_dir"]))


    raise ValueError(
        f"Unknown adapter type {adapter_type!r}. "
        "Supported types: 'openai_compatible', 'recorded'."
    )


def _require_keys(config: dict, keys: list[str], adapter_type: str) -> None:
    """Raise ValueError if any of *keys* are missing from *config*."""
    missing = [k for k in keys if k not in config]
    if missing:
        raise ValueError(
            f"Adapter type {adapter_type!r} requires missing config keys: {missing}"
        )


__all__ = [
    "get_adapter",
    "BaseAdapter",
    "AdapterCapabilities",
    "SUPPORTED_CAPABILITIES",
    "OpenAICompatibleAdapter",
    "RecordedAdapter",
]
