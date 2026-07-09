"""CLI tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from prompt_manager.cli import app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def store_dir():
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def prompt_file():
    content = "You are a helpful assistant. Be concise."
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write(content)
        return Path(f.name)


class TestPush:
    def test_push_new(self, runner, store_dir, prompt_file):
        result = runner.invoke(
            app,
            [
                "push",
                "test:prompt",
                "--file",
                str(prompt_file),
                "--version",
                "v1",
                "--env",
                "staging",
            ],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        assert result.exit_code == 0
        assert "v1" in result.stdout
        assert "staging" in result.stdout

    def test_push_missing_file(self, runner, store_dir):
        result = runner.invoke(
            app,
            ["push", "test:prompt", "--file", "/nonexistent", "--version", "v1"],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        assert result.exit_code != 0


class TestGet:
    def test_get_existing(self, runner, store_dir, prompt_file):
        runner.invoke(
            app,
            ["push", "test:prompt", "--file", str(prompt_file), "--version", "v1"],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        result = runner.invoke(app, ["get", "test:prompt"], env={"PROMPT_MANAGER_DIR": store_dir})
        assert result.exit_code == 0
        assert "test:prompt" in result.stdout

    def test_get_missing(self, runner, store_dir):
        result = runner.invoke(app, ["get", "nonexistent"], env={"PROMPT_MANAGER_DIR": store_dir})
        assert result.exit_code == 1


class TestList:
    def test_list_empty(self, runner, store_dir):
        result = runner.invoke(app, ["list"], env={"PROMPT_MANAGER_DIR": store_dir})
        assert result.exit_code == 0
        assert "No prompts" in result.stdout

    def test_list_with_items(self, runner, store_dir, prompt_file):
        runner.invoke(
            app,
            ["push", "test:prompt", "--file", str(prompt_file), "--version", "v1"],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        result = runner.invoke(app, ["list"], env={"PROMPT_MANAGER_DIR": store_dir})
        assert result.exit_code == 0
        assert "test:prompt" in result.stdout


class TestRollback:
    def test_rollback(self, runner, store_dir, prompt_file):
        runner.invoke(
            app,
            [
                "push",
                "test:prompt",
                "--file",
                str(prompt_file),
                "--version",
                "v1",
                "--env",
                "production",
            ],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        prompt_file2 = Path(str(prompt_file) + ".v2")
        prompt_file2.write_text("v2 content")
        runner.invoke(
            app,
            [
                "push",
                "test:prompt",
                "--file",
                str(prompt_file2),
                "--version",
                "v2",
                "--env",
                "production",
            ],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )

        result = runner.invoke(
            app,
            ["rollback", "test:prompt", "--to", "v1", "--env", "production"],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        assert result.exit_code == 0
        assert "v1" in result.stdout


class TestPromote:
    def test_promote(self, runner, store_dir, prompt_file):
        runner.invoke(
            app,
            [
                "push",
                "test:prompt",
                "--file",
                str(prompt_file),
                "--version",
                "v1",
                "--env",
                "staging",
            ],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        result = runner.invoke(
            app,
            ["promote", "test:prompt", "--from", "staging", "--to", "production"],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        assert result.exit_code == 0
        assert "production" in result.stdout


class TestABTest:
    def test_start(self, runner, store_dir, prompt_file):
        runner.invoke(
            app,
            [
                "push",
                "test:prompt",
                "--file",
                str(prompt_file),
                "--version",
                "v1",
                "--env",
                "production",
            ],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        runner.invoke(
            app,
            [
                "push",
                "test:prompt",
                "--file",
                str(prompt_file),
                "--version",
                "v2",
                "--env",
                "staging",
            ],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )

        result = runner.invoke(
            app,
            [
                "ab-test",
                "start",
                "test:prompt",
                "--variants",
                "v2:20,v1:80",
                "--control",
                "v1",
            ],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        assert result.exit_code == 0

    def test_invalid_weights(self, runner, store_dir, prompt_file):
        runner.invoke(
            app,
            ["push", "test:prompt", "--file", str(prompt_file), "--version", "v1"],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        result = runner.invoke(
            app,
            [
                "ab-test",
                "start",
                "test:prompt",
                "--variants",
                "v2:50,v1:30",
                "--control",
                "v1",
            ],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        assert result.exit_code != 0


class TestDiff:
    def test_diff_identical(self, runner, store_dir):
        from pathlib import Path

        f1 = Path(store_dir) / "p1.txt"
        f2 = Path(store_dir) / "p2.txt"
        f1.write_text("Hello")
        f2.write_text("Hello")

        runner.invoke(
            app,
            ["push", "test:prompt", "--file", str(f1), "--version", "v1"],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        runner.invoke(
            app,
            ["push", "test:prompt", "--file", str(f2), "--version", "v2"],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        result = runner.invoke(
            app,
            ["diff", "test:prompt", "--v1", "v1", "--v2", "v2"],
            env={"PROMPT_MANAGER_DIR": store_dir},
        )
        assert result.exit_code == 0
        assert "No content difference" in result.stdout
