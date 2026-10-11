# Contributing to ModelParity

Thank you for your interest in contributing to ModelParity!

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/modelparity/modelparity.git
   cd modelparity
   ```

2. Set up a virtual environment with Python 3.11+:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install in editable mode with development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

## Running Tests

Run the full pytest suite:
```bash
pytest -v
```

Run linting with ruff:
```bash
ruff check .
```

## Project Structure

- `src/modelparity/`: Core package
  - `schema.py`: Pydantic models for declarative YAML suite format
  - `adapters/`: Endpoint adapters (OpenAI-compatible, Recorded fixtures)
  - `assertions/`: Deterministic behavior assertions
  - `runner.py`: Async test execution coordinator
  - `compare.py`: Outcome classification and regression detection
  - `artifacts.py`: Atomic artifact writing and JSONL streaming
  - `reporter.py`: Markdown report generator
  - `redaction.py`: Secret scrubbing policy
  - `cli.py`: Typer CLI entrypoints
- `examples/`: Offline demo and sample configurations
- `tests/`: Unit and integration test suites

## Adding a New Assertion

1. Define the Pydantic schema model in `src/modelparity/schema.py` under the `Assertion` union.
2. Implement the evaluator function in `src/modelparity/assertions/evaluator.py`.
3. Register the assertion in `_EVALUATORS` and `SuiteValidator.SUPPORTED_ASSERTION_TYPES`.
4. Add unit tests in `tests/test_assertions.py`.
