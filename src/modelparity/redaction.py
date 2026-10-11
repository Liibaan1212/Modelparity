"""Redaction utilities for ModelParity.

:class:`RedactionPolicy` is the single place where all secret-scrubbing
logic lives.  It is used by the artifact writer, the HTTP request logger,
and the CLI before any output is written to disk or displayed to the user.

Design principles
-----------------
* **Never log** raw secret values — even temporarily.  Functions that need
  to look up environment variables for scanning purposes return only the
  *redacted* form of text, never the raw value.
* Redaction is **conservative**: when in doubt, redact.
* Placeholders are conspicuous so that users notice redacted content
  rather than silently losing information.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse, urlunparse


class RedactionPolicy:
    """Centralized redaction policy for ModelParity artifacts and logs.

    All methods are stateless and can be called on a shared instance.

    Attributes:
        REDACTED_PLACEHOLDER: The string substituted for sensitive values.
        SENSITIVE_HEADERS: Lower-cased header names whose values are always
            redacted, regardless of their content.
    """

    REDACTED_PLACEHOLDER: str = "[REDACTED]"

    #: Header names (lower-cased) that always have their values replaced.
    SENSITIVE_HEADERS: list[str] = [
        "authorization",
        "x-api-key",
        "api-key",
        "x-goog-api-key",
    ]

    # ------------------------------------------------------------------
    # Header redaction
    # ------------------------------------------------------------------

    def redact_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Return a copy of *headers* with sensitive values replaced.

        The comparison is case-insensitive, so ``Authorization``,
        ``AUTHORIZATION``, and ``authorization`` are all redacted.

        Args:
            headers: Mapping of header name → header value.

        Returns:
            A new dict with the same keys but sensitive values replaced by
            :attr:`REDACTED_PLACEHOLDER`.
        """
        redacted: dict[str, str] = {}
        for name, value in headers.items():
            if name.lower() in self.SENSITIVE_HEADERS:
                redacted[name] = self.REDACTED_PLACEHOLDER
            else:
                redacted[name] = value
        return redacted

    # ------------------------------------------------------------------
    # URL redaction
    # ------------------------------------------------------------------

    def redact_url(self, url: str) -> str:
        """Strip userinfo, query parameters, and fragments from *url*.

        * ``userinfo`` (``user:pass@``) is replaced with
          ``[REDACTED]@`` so the host is still visible.
        * Query string is dropped entirely (may contain API keys).
        * Fragment is dropped.

        Args:
            url: A URL string, possibly containing sensitive components.

        Returns:
            A sanitized URL string safe to include in artifacts and logs.
        """
        try:
            parsed = urlparse(url)
        except ValueError:
            # Unparseable URL — return a full redaction
            return self.REDACTED_PLACEHOLDER

        netloc = parsed.netloc

        # Remove userinfo (user:password@host → host)
        if "@" in netloc:
            host_part = netloc.rsplit("@", 1)[1]
            netloc = f"{self.REDACTED_PLACEHOLDER}@{host_part}"

        sanitized = urlunparse(
            (
                parsed.scheme,
                netloc,
                parsed.path,
                "",   # params
                "",   # query — dropped
                "",   # fragment — dropped
            )
        )
        return sanitized

    # ------------------------------------------------------------------
    # Secret scanning in text
    # ------------------------------------------------------------------

    def scan_for_secrets(self, text: str, known_secrets: list[str]) -> str:
        """Replace occurrences of *known_secrets* in *text* with the placeholder.

        Secrets are matched literally (no regex interpretation).  An empty
        string in *known_secrets* is skipped to avoid replacing every
        character.

        Args:
            text: Arbitrary text that may contain secret values.
            known_secrets: List of secret strings to scrub.  These are
                typically API key values retrieved via
                :meth:`redact_env_value`.

        Returns:
            *text* with all occurrences of each secret replaced by
            :attr:`REDACTED_PLACEHOLDER`.
        """
        for secret in known_secrets:
            if not secret:
                continue
            # Use re.escape so special regex characters in secrets are safe
            text = re.sub(re.escape(secret), self.REDACTED_PLACEHOLDER, text)
        return text

    # ------------------------------------------------------------------
    # Environment variable value retrieval for scanning
    # ------------------------------------------------------------------

    def redact_env_value(self, env_var_name: str) -> str:
        """Return the value of an env var, **only** for use in secret scanning.

        This method exists so callers can obtain a secret value to pass to
        :meth:`scan_for_secrets` without accidentally logging it.  The
        method itself never logs the value.

        Args:
            env_var_name: Name of the environment variable to read.

        Returns:
            The raw value of the environment variable, or an empty string
            if the variable is not set.  The empty string is safe to pass
            to :meth:`scan_for_secrets` — it will be skipped.

        .. warning::
            **Never** assign the return value to a variable that may be
            logged or included in output.  Pass it directly to
            :meth:`scan_for_secrets`.
        """
        return os.environ.get(env_var_name, "")

    # ------------------------------------------------------------------
    # Convenience: build secret list from common env var names
    # ------------------------------------------------------------------

    def collect_env_secrets(self, env_var_names: list[str]) -> list[str]:
        """Read multiple env vars and return their values for scanning.

        Empty values are included (they will be ignored by
        :meth:`scan_for_secrets`).

        Args:
            env_var_names: Env var names to read.

        Returns:
            List of raw values in the same order as *env_var_names*.
        """
        return [self.redact_env_value(name) for name in env_var_names]
