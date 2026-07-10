"""Integration tests for new prompt-manager features: canary, config, template validation."""

from __future__ import annotations

import tempfile

import pytest

from prompt_manager.canary import CanaryState, canary_deploy
from prompt_manager.schema import (
    PromptVersion,
)
from prompt_manager.storage import PromptStore


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as td:
        yield PromptStore(root=td)


class TestCanaryDeploy:
    def test_canary_state_creation(self):
        state = CanaryState(
            prompt_name="test:prompt",
            canary_version="v2",
            control_version="v1",
            weight=0.1,
        )
        assert state.prompt_name == "test:prompt"
        assert state.canary_version == "v2"
        assert state.weight == 0.1
        assert state.phase == "running"

    def test_canary_deploy_starts_ab_test(self, store):
        store.push_version("test:prompt", "production", PromptVersion(version="v1", content="v1"))
        store.push_version("test:prompt", "staging", PromptVersion(version="v2", content="v2"))

        state = canary_deploy(store, "test:prompt", "v2", "v1", weight=0.1)
        assert state is not None
        assert state.canary_version == "v2"

        entry = store.get("test:prompt")
        assert len(entry.ab_tests) == 1


class TestTemplateValidation:
    def test_validate_clean(self):
        pv = PromptVersion(version="v1", content="Hello {{name}}", template_vars={"name": "World"})
        result = pv.validate_templates()
        assert result["ok"] is True
        assert result["missing"] == []
        assert result["unused"] == []

    def test_validate_missing(self):
        pv = PromptVersion(version="v1", content="Hello {{name}} {{city}}")
        result = pv.validate_templates()
        assert "name" in result["missing"]
        assert "city" in result["missing"]

    def test_validate_unused(self):
        pv = PromptVersion(version="v1", content="Hello", template_vars={"name": "World"})
        result = pv.validate_templates()
        assert "name" in result["unused"]

    def test_validate_mixed(self):
        pv = PromptVersion(version="v1", content="{{a}}", template_vars={"a": "x", "b": "y"})
        result = pv.validate_templates()
        assert result["ok"] is False
        assert "b" in result["unused"]

    def test_validate_empty(self):
        pv = PromptVersion(version="v1", content="No variables here")
        result = pv.validate_templates()
        assert result["ok"] is True


class TestConfig:
    def test_config_importable(self):
        from prompt_manager.config import get, load_config

        c = load_config()
        assert "prompt_dir" in c
        assert get("canary.default_weight") == 10
