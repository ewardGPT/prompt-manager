"""Storage tests."""

from __future__ import annotations

import tempfile

import pytest

from prompt_manager.schema import ABVariant, PromptVersion
from prompt_manager.storage import PromptStore


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as td:
        yield PromptStore(root=td)


class TestPromptStore:
    def test_push_and_get(self, store):
        entry = store.push_version(
            "test:prompt", "staging", PromptVersion(version="v1", content="System prompt")
        )
        assert entry.name == "test:prompt"
        assert entry.current_version("staging") == "v1"

        got = store.get("test:prompt")
        assert got.name == entry.name
        assert got.current_version("staging") == "v1"

    def test_push_multiple_environments(self, store):
        store.push_version("test:prompt", "staging", PromptVersion(version="v1", content="v1"))
        store.push_version("test:prompt", "production", PromptVersion(version="v2", content="v2"))

        assert store.pull_version("test:prompt", "staging") == "v1"
        assert store.pull_version("test:prompt", "production") == "v2"

    def test_push_same_version_updates(self, store):
        store.push_version("test:prompt", "staging", PromptVersion(version="v1", content="first"))
        store.push_version("test:prompt", "staging", PromptVersion(version="v1", content="updated"))

        entry = store.get("test:prompt")
        assert len(entry.versions) == 1
        assert entry.versions[0].content == "updated"

    def test_rollback(self, store):
        store.push_version("test:prompt", "production", PromptVersion(version="v1", content="v1"))
        store.push_version("test:prompt", "production", PromptVersion(version="v2", content="v2"))
        store.rollback("test:prompt", "production", "v1")

        entry = store.get("test:prompt")
        assert entry.current_version("production") == "v1"

    def test_list_all(self, store):
        store.push_version("a:prompt", "staging", PromptVersion(version="v1", content="a"))
        store.push_version("b:prompt", "staging", PromptVersion(version="v1", content="b"))
        assert len(store.list_all()) == 2

    def test_ab_test(self, store):
        store.push_version("test:prompt", "staging", PromptVersion(version="v1", content="v1"))
        store.push_version("test:prompt", "staging", PromptVersion(version="v2", content="v2"))
        store.push_version("test:prompt", "production", PromptVersion(version="v1", content="v1"))

        entry = store.start_ab_test(
            "test:prompt",
            [ABVariant(version="v2", weight=0.1), ABVariant(version="v1", weight=0.9)],
            control="v1",
        )
        assert len(entry.ab_tests) == 1

        entry = store.stop_ab_test("test:prompt", "ab-1", winner="v2")
        assert entry.current_version("production") == "v2"

    def test_get_missing(self, store):
        with pytest.raises(KeyError, match="not found"):
            store.get("nonexistent")
