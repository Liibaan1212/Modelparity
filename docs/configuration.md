# Configuration Reference

A ModelParity test suite is defined in YAML or JSON using the schema below.

```yaml
version: 1

suite:
  name: "example-suite"
  description: "Suite description"
  capture:
    response_text: true      # Save assistant response text in results.jsonl
    redact_secrets: true     # Strip authorization headers and keys
    save_endpoint_url: false # Exclude full URLs from exported run manifests

endpoints:
  reference:
    adapter: openai_compatible # or "recorded"
    base_url: "http://127.0.0.1:8001/v1"
    model: "llama-3-8b"
    api_key_env: "REF_API_KEY"
    capabilities:
      - chat_completions
      - finish_reason
  candidate:
    adapter: openai_compatible
    base_url: "http://127.0.0.1:8002/v1"
    model: "llama-3-8b-quant"
    api_key_env: "CAND_API_KEY"

defaults:
  timeout_seconds: 60
  temperature: 0.0
  max_tokens: 128
  seed: 42

tests:
  - id: extract-order
    description: "Extract order details as JSON"
    labels: ["json", "smoke"]
    messages:
      - role: system
        content: "Return JSON matching the schema."
      - role: user
        content: "Order 3 teas."
    response_format:
      type: json_object
    generation_overrides:
      candidate:
        temperature: 0.1
    assertions:
      - type: response_received
      - type: non_empty_response
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
        equals: 3
```
