"""Recorded (fixture-backed) adapter for ModelParity.

Plays back pre-recorded NormalizedResponse fixtures from disk, making
zero network requests. Ideal for deterministic CI testing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from modelparity.adapters.base import AdapterCapabilities, BaseAdapter, SUPPORTED_CAPABILITIES
from modelparity.models import NormalizedResponse, ToolCall

logger = logging.getLogger(__name__)


class RecordedAdapter(BaseAdapter):
    """Offline adapter that serves responses from JSON fixture files.

    Each fixture file is a JSON document whose top-level structure is
    compatible with :class:`~modelparity.models.NormalizedResponse`.
    The file is named ``{test_id}.json`` inside *fixtures_dir*.

    This adapter makes **no network requests whatsoever**.

    Parameters
    ----------
    fixtures_dir:
        Directory containing ``{test_id}.json`` fixture files.
        The directory must exist; missing files produce error responses.

    Examples
    --------
    .. code-block:: python

        adapter = RecordedAdapter(fixtures_dir=Path("tests/fixtures"))
        response = await adapter.send({"test_id": "tc_001"}, timeout=0)
    """

    def __init__(self, fixtures_dir: Path) -> None:
        self._fixtures_dir = Path(fixtures_dir)
        self._fixtures: dict[str, NormalizedResponse] = {}
        self._load_fixtures()

    # ------------------------------------------------------------------
    # BaseAdapter interface
    # ------------------------------------------------------------------

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Recorded responses can represent any capability."""
        return AdapterCapabilities(supported=list(SUPPORTED_CAPABILITIES))

    async def send(
        self,
        request_spec: dict,
        timeout: float = 0.0,  # noqa: ASYNC109 – no I/O, timeout ignored
    ) -> NormalizedResponse:
        """Return the pre-recorded response for the given test ID.

        The ``timeout`` parameter is accepted for interface compatibility
        but is never used—no I/O occurs.

        Parameters
        ----------
        request_spec:
            Must contain a ``test_id`` key matching a loaded fixture.
        timeout:
            Ignored.

        Returns
        -------
        NormalizedResponse
            The loaded fixture, or an error response if not found.
        """
        test_id: str = request_spec.get("test_id", "")
        if not test_id:
            return NormalizedResponse(
                test_id="",
                error="request_spec missing required 'test_id' field.",
                error_code="REQUEST_ERROR",
            )

        fixture = self._fixtures.get(test_id)
        if fixture is None:
            return NormalizedResponse(
                test_id=test_id,
                error=(
                    f"No fixture found for test_id={test_id!r}. "
                    f"Expected file: {self._fixtures_dir / (test_id + '.json')}"
                ),
                error_code="REQUEST_ERROR",
            )

        return fixture

    def get_manifest(self) -> dict:
        """Return safe metadata describing this recorded adapter.

        Returns
        -------
        dict
            Keys: ``adapter``, ``fixtures_dir`` (basename only),
            ``fixture_count``, ``capabilities``.
        """
        return {
            "adapter": "recorded",
            "fixtures_dir": self._fixtures_dir.name,
            "fixture_count": len(self._fixtures),
            "capabilities": list(SUPPORTED_CAPABILITIES),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_fixtures(self) -> None:
        """Load all ``*.json`` files from :attr:`_fixtures_dir`.

        Files that cannot be parsed are logged as warnings and skipped.
        """
        if not self._fixtures_dir.exists():
            logger.warning(
                "Fixtures directory %r does not exist. "
                "All send() calls will return error responses.",
                str(self._fixtures_dir),
            )
            return

        json_files = list(self._fixtures_dir.glob("*.json"))
        if not json_files:
            logger.warning(
                "No *.json fixture files found in %r.",
                str(self._fixtures_dir),
            )
            return

        for path in json_files:
            test_id = path.stem
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                response = self._parse_fixture(raw, test_id)
                self._fixtures[test_id] = response
            except json.JSONDecodeError as exc:
                logger.warning("Skipping fixture %r – invalid JSON: %s", str(path), exc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping fixture %r – parse error: %s", str(path), exc)

        logger.debug(
            "RecordedAdapter loaded %d fixture(s) from %r.",
            len(self._fixtures),
            str(self._fixtures_dir),
        )

    @staticmethod
    def _parse_fixture(raw: dict, test_id: str) -> NormalizedResponse:
        """Build a NormalizedResponse from a raw fixture dict.

        The fixture may be:
        - A full NormalizedResponse JSON (field names match the model).
        - A raw OpenAI-format response body (has a ``choices`` key).

        Parameters
        ----------
        raw:
            Parsed JSON dict from the fixture file.
        test_id:
            The test ID inferred from the filename (used as fallback).

        Returns
        -------
        NormalizedResponse
        """
        # If the fixture already uses NormalizedResponse field names, load directly.
        if "content" in raw or "error" in raw or "finish_reason" in raw:
            data = dict(raw)
            data.setdefault("test_id", test_id)

            # Deserialise nested ToolCall dicts if present
            if "tool_calls" in data and isinstance(data["tool_calls"], list):
                data["tool_calls"] = [
                    ToolCall(**tc) if isinstance(tc, dict) else tc
                    for tc in data["tool_calls"]
                ]
            return NormalizedResponse.model_validate(data)

        # Otherwise treat it as a raw OpenAI-format response.
        choice: dict = {}
        if raw.get("choices"):
            choice = raw["choices"][0]

        message: dict = choice.get("message", {})
        tool_calls: list[ToolCall] = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function", {})
            tool_calls.append(
                ToolCall(
                    id=tc.get("id", ""),
                    name=fn.get("name", ""),
                    arguments=fn.get("arguments", ""),
                )
            )

        return NormalizedResponse(
            test_id=test_id,
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason"),
            model=raw.get("model"),
            usage=raw.get("usage"),
            raw=raw,
        )
