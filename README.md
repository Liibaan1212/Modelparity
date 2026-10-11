# ModelParity

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Local First](https://img.shields.io/badge/privacy-local--first-green.svg)](#security-privacy-and-redaction)

A local-first, developer-centric CLI for running **portable behavior-contract tests** across LLM-serving configurations.

> [!IMPORTANT]
> **What ModelParity does NOT claim to prove:**
> ModelParity is **not** intended to prove bit-for-bit or logit-level model parity. It checks whether user-defined application behaviors—such as emitting valid JSON, returning expected tool calls, or respecting stop reasons—remain intact when an open-weight model is moved across inference runtimes, quantization levels, prompt templates, or serving backends. Structural validity does not imply semantic correctness.

---

## Table of Contents

- [The Workflow](#the-workflow)
- [Quick Start (Offline Demo)](#quick-start-offline-demo)
- [Local Endpoint Example](#local-endpoint-example)
- [Comparison Semantics](#comparison-semantics)
- [Supported Assertions](#supported-assertions)
- [Adapter Capabilities](#adapter-capabilities)
- [Security, Privacy, and Redaction](#security-privacy-and-redaction)
- [Reproducibility Bundle](#reproducibility-bundle)
- [CLI Reference](#cli-reference)
- [Contributing](#contributing)
- [Prior Art and Related Tools](#prior-art-and-related-tools)

---

## The Workflow

When an engineer migrates an open-weight model between serving configurations (e.g., from vLLM to llama.cpp, FP16 to GGUF Q4_K_M, or updating chat templates), they need to answer:

> *"Did this serving migration break any behaviors my application depends on, and can another engineer reproduce the failure bundle?"*

ModelParity provides an end-to-end contract validation workflow:
1. **Define contracts:** Author test cases in a declarative YAML format specifying messages and deterministic assertions (JSON Schema, tool call envelopes, stop reasons, etc.).
2. **Execute comparison:** Run tests against two endpoints (`reference` and `candidate`) or replay pre-recorded response fixtures.
3. **Classify discrepancies:** Distinguish regressions (`PASS -> FAIL`) from baseline failures and innocent prose differences.
4. **Export diagnostic bundle:** Produce an atomic reproducibility bundle with non-secret metadata, raw responses (when enabled), and a Markdown report.

---

## Quick Start (Offline Demo)

ModelParity runs completely offline with no network requests, model weights, or GPU needed:

```bash
# 1. Install modelparity
pip install modelparity

# 2. Validate the offline demo suite
modelparity validate examples/offline-demo/parity.yaml

# 3. Preflight check endpoints and fixtures
modelparity doctor examples/offline-demo/parity.yaml

# 4. Execute the suite and produce artifacts
modelparity run examples/offline-demo/parity.yaml --out ./demo-run

# 5. Inspect the generated report
modelparity report ./demo-run
```

---

## Local Endpoint Example

Compare an existing reference server with a new candidate setup (e.g., vLLM vs. llama.cpp server):

```yaml
version: 1
suite:
  name: "migration-smoke-test"
  description: "Check JSON and tool calling contracts during serving migration"
  capture:
    response_text: true
    redact_secrets: true
    save_endpoint_url: false

endpoints:
  reference:
    adapter: openai_compatible
    base_url: "http://127.0.0.1:8001/v1"
    model: "llama-3-8b-instruct-fp16"
    api_key_env: "REF_API_KEY"
    capabilities:
      - chat_completions
      - finish_reason
  candidate:
    adapter: openai_compatible
    base_url: "http://127.0.0.1:8002/v1"
    model: "llama-3-8b-instruct-q4"
    api_key_env: "CAND_API_KEY"
    capabilities:
      - chat_completions
      - finish_reason

defaults:
  timeout_seconds: 45
  temperature: 0.0

tests:
  - id: extract-user-order
    description: "Model must return valid JSON matching the order schema"
    messages:
      - role: system
        content: "Extract product and quantity as JSON."
      - role: user
        content: "Order 2 coffees."
    assertions:
      - type: response_received
      - type: valid_json
      - type: json_schema
        schema:
          type: object
          properties:
            product: {type: string}
            quantity: {type: integer}
          required: [product, quantity]
      - type: json_value
        path: "$.quantity"
        equals: 2
```

---

## Comparison Semantics

ModelParity evaluates assertions independently on the reference and candidate endpoints and classifies results into a stable taxonomy:

| Status | Meaning |
|---|---|
| `PASS` | Both endpoints satisfied all configured assertions. |
| `REGRESSION` | Reference satisfied all assertions, but candidate failed one or more assertions. |
| `CONTRACT_FAIL` | Candidate failed an assertion, and reference also failed (contract was never met). |
| `BASELINE_FAIL` | Reference endpoint failed its own baseline assertions. Comparison is not a valid regression test. |
| `REQUEST_ERROR` | Network timeout, connection error, or HTTP protocol failure. |
| `INCONCLUSIVE` | Required capability was missing, or metadata mismatch invalidates safe comparison. |
| `SKIPPED` | Test requires an unsupported adapter capability. |

---

## Supported Assertions

Deterministic assertions verify explicit behavior contracts without relying on opaque LLM judges:

| Assertion Type | Parameters | Description |
|---|---|---|
| `response_received` | None | Verifies response arrived within configured timeout with 2xx status. |
| `non_empty_response` | None | Checks assistant response text is non-empty after stripping. |
| `valid_json` | None | Verifies response string parses as valid JSON. |
| `json_schema` | `schema: dict` | Validates parsed JSON against a JSON Schema draft-07. |
| `json_value` | `path: str`, `equals: Any` | Inspects value at dotted path (e.g. `$.quantity`) for equality. |
| `exact_match` | `expected: str` | Exact string equality (case-sensitive). |
| `normalized_match` | `expected: str`, `normalize: list` | Equality after normalization (`lowercase`, `strip`, `collapse_whitespace`). |
| `tool_call_name` | `expected_name: str` | Verifies tool call matches expected function name. |
| `tool_call_args_schema` | `schema: dict` | Validates tool call arguments JSON against JSON Schema. |
| `finish_reason` | `expected: str` | Validates completion stop indicator (e.g. `stop`, `length`, `tool_calls`). |

---

## Adapter Capabilities

Endpoints declare supported capabilities. Tests requiring capabilities not advertised by an endpoint are flagged:

- `chat_completions`: Standard OpenAI-compatible `/chat/completions` API.
- `tool_calls`: Structured function/tool calling envelopes.
- `json_schema`: Constrained JSON schema generation.
- `finish_reason`: Exposing explicit completion finish reasons.
- `seed`: Deterministic sampling seed support.
- `usage_tokens`: Exposing prompt and completion token counts.

---

## Security, Privacy, and Redaction

ModelParity is designed with privacy-by-default:

- **Zero telemetry:** No background analytics, phone-home requests, or third-party pings.
- **Header scrubbing:** `Authorization`, `X-API-KEY`, and other credentials are never written to logs or artifacts.
- **URL sanitization:** Basic authentication credentials and URL query parameters are stripped before writing manifests.
- **Configurable response capture:** Set `capture.response_text: false` to omit raw model outputs entirely.
- **Replay isolation:** `modelparity replay` makes zero network requests.

---

## Reproducibility Bundle

Every `modelparity run` creates an atomic directory containing:

```
modelparity-run-<timestamp>/
├── run.json         # Non-secret run manifest, software versions, endpoint metadata
├── suite.json       # Sanitized copy of the test suite and its SHA-256 hash
├── results.jsonl    # Line-by-line streaming records of requests, assertions, and status
├── summary.json     # Aggregate pass/fail/regression statistics
└── report.md        # Human-readable Markdown report ready to attach to an issue
```

---

## CLI Reference and Exit Codes

```text
modelparity init [--out parity.yaml] [--force]
modelparity validate <suite_file> [--strict]
modelparity run <suite_file> [--out DIR] [--only TAG] [--concurrency N]
modelparity report <run_dir> [--out FILE]
modelparity replay <run_dir> [--out FILE]
modelparity doctor <suite_file>
```

### Exit Codes for CI

- `0`: All assertions passed; no blocking regressions detected.
- `1`: One or more contract assertions failed or regressed.
- `2`: Invalid test suite configuration or schema validation error.
- `3`: Infrastructure, timeout, or network connection error.
- `4`: Comparison was inconclusive due to capability mismatch.

---

## Prior Art and Related Tools

ModelParity builds upon and complements excellent existing tools:

- [llama.cpp model-conversion](https://github.com/ggml-org/llama.cpp/blob/master/examples/model-conversion/README.md): Low-level logit comparison, quantization, and perplexity verification.
- [EleutherAI lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness): Comprehensive academic language-model benchmarks.
- [Promptfoo](https://www.promptfoo.dev/): Multi-model prompt and security testing framework.
- [vLLM](https://github.com/vllm-project/vllm): High-throughput serving engine with structured output support.
- [OpenAI Evals](https://github.com/openai/evals): General-purpose model evaluation registry.

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for local development setup and guidelines.

## License

ModelParity is open source software licensed under the [Apache-2.0 License](LICENSE).
