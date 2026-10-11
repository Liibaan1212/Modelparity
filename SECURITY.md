# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability or sensitive data leak risk in ModelParity:

1. **Do not open a public GitHub issue.**
2. Send an email to the maintainers at `security@modelparity.dev` or use GitHub Private Vulnerability Reporting.
3. Include:
   - Description of the issue
   - Reproduction steps or suite file
   - Impact assessment
4. We aim to acknowledge reports within 48 hours and provide a fix or mitigation plan within 7 business days.

## Privacy and Data Handling

ModelParity is designed with privacy-by-default:

- **Local-first execution:** Offline tests make zero network requests.
- **Secret scrubbing:** Credentials in headers, query parameters, and environment variables are scrubbed using `RedactionPolicy`.
- **Zero telemetry:** No usage tracking, phone-home metrics, or remote analytics are collected.
- **Opt-in response capture:** Raw model outputs can be excluded from artifacts via `capture.response_text: false`.
