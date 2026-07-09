"""Additional CLI tests for prompt-manager — edge cases and output format checks."""

from __future__ import annotations

import tempfile

import pytest
from typer.testing import CliRunner

from prompt_manager.cli import app
from prompt_manager.schema import PromptVersion
from prompt_manager.storage import PromptStore


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def store_dir():
    with tempfile.TemporaryDirectory() as td:
        # Seed with multiple prompts
        store = PromptStore(root=td)
        for i in range(5):
            pv = PromptVersion(version=f"v{i}", content=f"content-{i}")
            store.push_version(f"agent-{i}:prompt", "staging", pv)
        yield td


PROMPT_ENVS = ["dev", "test", "qa"]


@pytest.mark.parametrize("env_val", PROMPT_ENVS)
def test_list_with_env_filter(runner, store_dir, env_val):
    result = runner.invoke(
        app,
        ["list", "--env", env_val],
        env={"PROMPT_MANAGER_DIR": store_dir},
    )
    assert result.exit_code == 0


class TestDiffEdgeCases:
    def test_diff_missing_v1(self, runner):
        result = runner.invoke(
            app,
            ["diff", "test:prompt", "--v1", "nonexistent", "--v2", "v1"],
            env={"PROMPT_MANAGER_DIR": "/tmp/nonexistent"},
        )
        assert result.exit_code != 0

    def test_diff_missing_v2(self, runner):
        result = runner.invoke(
            app,
            ["diff", "test:prompt", "--v1", "v1", "--v2", "nonexistent"],
            env={"PROMPT_MANAGER_DIR": "/tmp/nonexistent"},
        )
        assert result.exit_code != 0


class TestPromoteEdgeCases:
    def test_promote_missing_env(self, runner):
        result = runner.invoke(
            app,
            ["promote", "nonexistent", "--from", "staging", "--to", "production"],
            env={"PROMPT_MANAGER_DIR": "/tmp/nonexistent"},
        )
        assert result.exit_code != 0


class TestValidateEdgeCases:
    def test_validate_missing_env(self, runner):
        result = runner.invoke(
            app,
            ["validate", "nonexistent", "--env", "production"],
            env={"PROMPT_MANAGER_DIR": "/tmp/nonexistent"},
        )
        assert result.exit_code != 0


class TestConfigCommand:
    def test_config_set_eval_suite(self, runner, store_dir):
        result = runner.invoke(
            app,
            ["config", "agent-0:prompt", "--eval-suite", "test:gate"],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        assert result.exit_code == 0

    def test_config_no_options(self, runner, store_dir):
        result = runner.invoke(
            app,
            ["config", "agent-0:prompt"],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        assert result.exit_code == 0


class TestABTestList:
    def test_ab_list_empty(self, runner, store_dir):
        result = runner.invoke(
            app,
            ["ab-test", "list"],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        assert result.exit_code == 0

    def test_ab_list_with_name_filter(self, runner, store_dir):
        result = runner.invoke(
            app,
            ["ab-test", "list", "--name", "agent-0:prompt"],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        assert result.exit_code == 0
