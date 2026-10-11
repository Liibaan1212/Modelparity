"""Abstract adapter base and capability declarations for ModelParity."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modelparity.models import NormalizedResponse

# ---------------------------------------------------------------------------
# Capability registry
# ---------------------------------------------------------------------------

SUPPORTED_CAPABILITIES: list[str] = [
    "chat_completions",
    "tool_calls",
    "json_schema",
    "finish_reason",
    "seed",
    "usage_tokens",
]
"""All capability strings recognised by ModelParity.

``chat_completions``
    The adapter can send chat-style messages and receive a completion.

``tool_calls``
    The adapter supports the ``tools`` / function-calling field.

``json_schema``
    The adapter supports ``response_format`` with a JSON schema.

``finish_reason``
    The adapter reliably returns a ``finish_reason`` in the response.

``seed``
    The adapter honours a ``seed`` parameter for reproducibility.

``usage_tokens``
    The adapter returns prompt / completion token counts.
"""


# ---------------------------------------------------------------------------
# Capability descriptor
# ---------------------------------------------------------------------------


@dataclass
class AdapterCapabilities:
    """Describes what an adapter can do.

    Parameters
    ----------
    supported:
        List of capability strings from :data:`SUPPORTED_CAPABILITIES`.
    """

    supported: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        unknown = set(self.supported) - set(SUPPORTED_CAPABILITIES)
        if unknown:
            raise ValueError(
                f"Unknown capabilities declared: {sorted(unknown)}. "
                f"Valid options are: {SUPPORTED_CAPABILITIES}"
            )

    def supports(self, cap: str) -> bool:
        """Return True if *cap* is in the supported capabilities list."""
        return cap in self.supported


# ---------------------------------------------------------------------------
# Abstract adapter
# ---------------------------------------------------------------------------


class BaseAdapter(ABC):
    """Abstract interface every ModelParity adapter must implement.

    Adapters are responsible for:

    1. Translating a provider-agnostic ``request_spec`` dict into a
       provider-specific API request.
    2. Executing the request (or loading from a fixture).
    3. Returning a :class:`~modelparity.models.NormalizedResponse`.

    Adapters **must never** store or leak API keys in any form.
    """

    @property
    @abstractmethod
    def capabilities(self) -> AdapterCapabilities:
        """Advertise which capabilities this adapter supports."""
        ...

    @abstractmethod
    async def send(
        self,
        request_spec: dict,
        timeout: float = 30.0,
    ) -> "NormalizedResponse":
        """Send *request_spec* to the model and return a normalized response.

        Parameters
        ----------
        request_spec:
            Provider-agnostic dict containing fields such as ``messages``,
            ``temperature``, ``seed``, ``response_format``, ``tools``, etc.
        timeout:
            Maximum seconds to wait for a response.

        Returns
        -------
        NormalizedResponse
            Always returns a response object; errors are encoded inside
            ``NormalizedResponse.error`` rather than raised.
        """
        ...

    @abstractmethod
    def get_manifest(self) -> dict:
        """Return safe, non-secret metadata about this adapter.

        The manifest is included in reports and comparison output.
        It **must not** contain API keys or full secret values.

        Returns
        -------
        dict
            Metadata dict. Recommended keys: ``adapter``, ``model``,
            ``capabilities``, and optionally ``base_url`` (redacted
            according to policy).
        """
        ...
