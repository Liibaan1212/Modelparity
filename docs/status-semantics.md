# ModelParity Status Semantics

ModelParity uses a strict taxonomy to classify test outcomes.

## Status Vocabulary

### `PASS`
- **Condition:** All configured assertions passed on both the reference and candidate endpoints.
- **Meaning:** The candidate satisfied the contract identically to the reference baseline.

### `REGRESSION`
- **Condition:** The reference baseline passed all assertions, but the candidate failed one or more assertions.
- **Meaning:** A behavior that worked on the previous serving configuration is broken in the candidate configuration. Triggers exit code `1`.

### `CONTRACT_FAIL`
- **Condition:** The candidate failed assertions that the reference baseline also failed.
- **Meaning:** Neither configuration meets the desired contract.

### `BASELINE_FAIL`
- **Condition:** The reference endpoint failed its own assertions.
- **Meaning:** The baseline is invalid. A candidate failure cannot be reliably interpreted as a regression.

### `REQUEST_ERROR`
- **Condition:** A network connection error, HTTP 4xx/5xx status, or request timeout occurred.
- **Meaning:** Infrastructure failure preventing valid response evaluation. Triggers exit code `3`.

### `INCONCLUSIVE`
- **Condition:** Insufficient metadata or endpoint capability mismatch.
- **Meaning:** Results cannot be safely compared. Triggers exit code `4`.

### `SKIPPED`
- **Condition:** A test requires capabilities not advertised by one of the endpoints.
- **Meaning:** The test was bypassed cleanly.

## CI Exit Codes

| Exit Code | Condition |
|---|---|
| `0` | All tests completed and no blocking regressions occurred. |
| `1` | One or more tests regressed or failed contract assertions. |
| `2` | Invalid test suite format, duplicate IDs, or configuration error. |
| `3` | Network, connection, or runner infrastructure error. |
| `4` | Inconclusive run due to capability mismatch. |
