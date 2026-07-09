"""Comprehensive prompt-manager storage tests."""

from __future__ import annotations

import tempfile

import pytest

from prompt_manager.schema import ABVariant, PromptVersion
from prompt_manager.storage import PromptStore


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as td:
        yield PromptStore(root=td)


@pytest.fixture
def v1_prompt():
    return PromptVersion(version="v1", content="You are helpful")


@pytest.fixture
def v2_prompt():
    return PromptVersion(version="v2", content="You are helpful and safe")


@pytest.fixture
def v3_prompt():
    return PromptVersion(version="v3", content="You are helpful, safe, and accurate")


class TestPushVersion:
    def test_creates_new_entry(self, store, v1_prompt):
        entry = store.push_version("test:prompt", "staging", v1_prompt)
        assert entry.name == "test:prompt"

    def test_adds_to_existing_entry(self, store, v1_prompt, v2_prompt):
        store.push_version("test:prompt", "staging", v1_prompt)
        entry = store.push_version("test:prompt", "staging", v2_prompt)
        assert len(entry.versions) == 2

    def test_multiple_environments(self, store, v1_prompt, v2_prompt):
        store.push_version("test:prompt", "staging", v1_prompt)
        store.push_version("test:prompt", "production", v2_prompt)
        entry = store.get("test:prompt")
        assert entry.environments["staging"] == "v1"
        assert entry.environments["production"] == "v2"

    @pytest.mark.parametrize("env", ["staging", "production", "development", "testing", "dev"])
    def test_various_envs(self, store, v1_prompt, env):
        store.push_version("test:prompt", env, v1_prompt)
        assert store.get("test:prompt").environments[env] == "v1"


class TestPullVersion:
    def test_pulls_correct_content(self, store, v1_prompt):
        store.push_version("test:prompt", "staging", v1_prompt)
        content = store.pull_version("test:prompt", "staging")
        assert content == "You are helpful"

    def test_pulls_different_envs(self, store, v1_prompt, v2_prompt):
        store.push_version("test:prompt", "staging", v1_prompt)
        store.push_version("test:prompt", "production", v2_prompt)
        assert store.pull_version("test:prompt", "staging") == "You are helpful"
        assert store.pull_version("test:prompt", "production") == "You are helpful and safe"

    def test_missing_env_raises(self, store, v1_prompt):
        store.push_version("test:prompt", "staging", v1_prompt)
        with pytest.raises(ValueError, match="No version assigned"):
            store.pull_version("test:prompt", "production")


class TestRollback:
    def test_valid_rollback(self, store, v1_prompt, v2_prompt):
        store.push_version("test:prompt", "production", v1_prompt)
        store.push_version("test:prompt", "production", v2_prompt)
        store.rollback("test:prompt", "production", "v1")
        assert store.get("test:prompt").environments["production"] == "v1"

    def test_invalid_version_raises(self, store, v1_prompt):
        store.push_version("test:prompt", "production", v1_prompt)
        with pytest.raises(ValueError, match="not found"):
            store.rollback("test:prompt", "production", "nonexistent")

    def test_rollback_missing_prompt_raises(self, store):
        with pytest.raises(KeyError, match="not found"):
            store.rollback("nonexistent", "production", "v1")


class TestABTests:
    def test_start_ab_test(self, store, v1_prompt, v2_prompt):
        store.push_version("test:prompt", "production", v1_prompt)
        store.push_version("test:prompt", "staging", v2_prompt)
        entry = store.start_ab_test(
            "test:prompt",
            [ABVariant(version="v2", weight=0.2), ABVariant(version="v1", weight=0.8)],
            control="v1",
        )
        assert len(entry.ab_tests) == 1

    def test_stop_ab_test_with_winner(self, store, v1_prompt, v2_prompt):
        store.push_version("test:prompt", "production", v1_prompt)
        store.push_version("test:prompt", "staging", v2_prompt)
        store.start_ab_test(
            "test:prompt",
            [ABVariant(version="v2", weight=0.2), ABVariant(version="v1", weight=0.8)],
            control="v1",
        )
        entry = store.stop_ab_test("test:prompt", "ab-1", winner="v2")
        assert entry.current_version("production") == "v2"

    def test_stop_missing_ab_test_raises(self, store, v1_prompt):
        store.push_version("test:prompt", "production", v1_prompt)
        with pytest.raises(KeyError, match="No running A/B test"):
            store.stop_ab_test("test:prompt", "nonexistent")


class TestListAll:
    def test_empty(self, store):
        assert store.list_all() == []

    def test_one(self, store, v1_prompt):
        store.push_version("a:prompt", "staging", v1_prompt)
        assert len(store.list_all()) == 1

    def test_many(self, store, v1_prompt):
        for i in range(10):
            store.push_version(f"agent-{i}:prompt", "staging", v1_prompt)
        assert len(store.list_all()) == 10


class TestGet:
    def test_existing(self, store, v1_prompt):
        store.push_version("test:prompt", "staging", v1_prompt)
        assert store.get("test:prompt").name == "test:prompt"

    def test_missing_raises(self, store):
        with pytest.raises(KeyError, match="not found"):
            store.get("nonexistent")


class TestPersistence:
    def test_index_persists(self, store, v1_prompt):
        store.push_version("test:prompt", "staging", v1_prompt)
        store2 = PromptStore(root=store.root)
        assert store2.get("test:prompt").name == "test:prompt"

    def test_data_survives_reopen(self, store, v1_prompt, v2_prompt):
        store.push_version("test:prompt", "staging", v1_prompt)
        store.push_version("test:prompt", "production", v2_prompt)
        store.rollback("test:prompt", "production", "v1")

        store2 = PromptStore(root=store.root)
        entry = store2.get("test:prompt")
        assert entry.current_version("production") == "v1"
        assert len(entry.versions) == 2
