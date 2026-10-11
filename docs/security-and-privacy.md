# Security and Privacy

ModelParity is designed with strong privacy and security guarantees.

## Privacy by Default

- **No Remote Telemetry:** ModelParity never collects analytics, pings remote servers, or tracks usage.
- **Local-First Execution:** When using the `recorded` adapter or local server URLs (`http://127.0.0.1`), all data stays on your machine.
- **Explicit Outbound Traffic:** Network calls are strictly limited to the user-declared endpoint URLs.

## Secret Redaction

ModelParity includes an automatic redaction filter (`RedactionPolicy`):

1. **HTTP Headers:** Any headers named `Authorization`, `X-API-KEY`, `API-KEY`, or `X-GOOG-API-KEY` (case-insensitive) have their values replaced with `[REDACTED]`.
2. **URLs:** Embedded credentials (`user:pass@host`) and query parameters (which frequently contain tokens or API keys) are stripped before writing manifests.
3. **Environment Secrets:** Secret values retrieved from environment variables are scanned and masked in diagnostic outputs.

## Safe Replay

The `replay` command reconstructs reports and assertions from saved local run artifacts without initiating any new HTTP or network requests.
