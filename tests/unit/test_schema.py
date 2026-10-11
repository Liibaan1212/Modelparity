"""Unit tests for ModelParity suite schema validation."""

import pytest
from pydantic import ValidationError

from modelparity.schema import SuiteValidator


def test_valid_suite_loads():
    raw = {
        "version": 1,
        "suite": {
            "name": "test-suite",
            "description": "Validation test suite",
        },
        "endpoints": {
            "reference": {
                "adapter": "recorded",
                "fixtures_dir": "tests/fixtures/ref",
            },
            "candidate": {
                "adapter": "recorded",
                "fixtures_dir": "tests/fixtures/cand",
            },
        },
        "defaults": {
            "timeout_seconds": 30,
            "temperature": 0.0,
            "max_tokens": 100,
        },
        "tests": [
            {
                "id": "t1",
                "messages": [{"role": "user", "content": "hi"}],
                "assertions": [
                    {"type": "response_received"},
                    {"type": "non_empty_response"},
                ],
            }
        ],
    }

    validator = SuiteValidator()
    suite = validator.validate_suite(raw)
    assert suite.suite.name == "test-suite"
    assert len(suite.tests) == 1
    assert suite.tests[0].id == "t1"


def test_duplicate_test_ids_rejected():
    raw = {
        "version": 1,
        "suite": {"name": "test-suite"},
        "endpoints": {
            "reference": {"adapter": "recorded", "fixtures_dir": "dir1"},
            "candidate": {"adapter": "recorded", "fixtures_dir": "dir2"},
        },
        "tests": [
            {
                "id": "duplicate-id",
                "messages": [{"role": "user", "content": "first"}],
                "assertions": [{"type": "non_empty_response"}],
            },
            {
                "id": "duplicate-id",
                "messages": [{"role": "user", "content": "second"}],
                "assertions": [{"type": "non_empty_response"}],
            },
        ],
    }

    validator = SuiteValidator()
    with pytest.raises(ValueError, match="Duplicate test IDs found"):
        validator.validate_suite(raw)


def test_unsupported_assertion_type_rejected():
    raw = {
        "version": 1,
        "suite": {"name": "test-suite"},
        "endpoints": {
            "reference": {"adapter": "recorded", "fixtures_dir": "dir1"},
            "candidate": {"adapter": "recorded", "fixtures_dir": "dir2"},
        },
        "tests": [
            {
                "id": "t1",
                "messages": [{"role": "user", "content": "hi"}],
                "assertions": [
                    {"type": "non_existent_assertion_type"},
                ],
            }
        ],
    }

    validator = SuiteValidator()
    with pytest.raises(ValidationError):
        validator.validate_suite(raw)


def test_missing_required_fields_rejected():
    raw = {
        "version": 1,
        # missing "suite" and "endpoints"
        "tests": [],
    }

    validator = SuiteValidator()
    with pytest.raises(ValidationError):
        validator.validate_suite(raw)


def test_capture_defaults():
    raw = {
        "version": 1,
        "suite": {"name": "test-suite"},
        "endpoints": {
            "reference": {"adapter": "recorded", "fixtures_dir": "dir1"},
            "candidate": {"adapter": "recorded", "fixtures_dir": "dir2"},
        },
        "tests": [
            {
                "id": "t1",
                "messages": [{"role": "user", "content": "hi"}],
                "assertions": [{"type": "non_empty_response"}],
            }
        ],
    }

    validator = SuiteValidator()
    suite = validator.validate_suite(raw)
    assert suite.suite.capture.response_text is True
    assert suite.suite.capture.redact_secrets is True
    assert suite.suite.capture.save_endpoint_url is False
