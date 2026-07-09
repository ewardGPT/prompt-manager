"""Schema tests."""

from __future__ import annotations

from prompt_manager.schema import (
    ABTestStatus,
    ABVariant,
    PromptEntry,
    PromptVersion,
)


class TestPromptVersion:
    def test_hash_computed(self):
        pv = PromptVersion(version="v1", content="Hello, world!")
        assert len(pv.hash) == 12
        # Same content = same hash
        pv2 = PromptVersion(version="v1", content="Hello, world!")
        assert pv.hash == pv2.hash

    def test_hash_different(self):
        pv1 = PromptVersion(version="v1", content="A")
        pv2 = PromptVersion(version="v1", content="B")
        assert pv1.hash != pv2.hash


class TestABTestConfig:
    def test_valid_split(self):
        variants = [
            ABVariant(version="v4", weight=0.1),
            ABVariant(version="v3", weight=0.9),
        ]
        from prompt_manager.schema import ABTestConfig

        cfg = ABTestConfig(id="test-1", variants=variants, control_version="v3")
        assert cfg.is_valid()

    def test_invalid_split(self):
        variants = [ABVariant(version="v4", weight=0.5)]
        from prompt_manager.schema import ABTestConfig

        cfg = ABTestConfig(id="test-1", variants=variants, control_version="v3")
        assert not cfg.is_valid()


class TestPromptEntry:
    def test_push_new_version(self):
        entry = PromptEntry(name="test:prompt")
        pv = PromptVersion(version="v1", content="System prompt v1")
        entry.push("staging", pv)
        assert entry.environments["staging"] == "v1"
        assert len(entry.versions) == 1

    def test_push_overwrite(self):
        entry = PromptEntry(name="test:prompt")
        pv1 = PromptVersion(version="v1", content="v1")
        pv2 = PromptVersion(version="v1", content="v1 updated")
        entry.push("staging", pv1)
        entry.push("staging", pv2)
        assert len(entry.versions) == 1  # same version, updated
        assert entry.versions[0].content == "v1 updated"

    def test_rollback(self):
        entry = PromptEntry(name="test:prompt")
        entry.push("staging", PromptVersion(version="v1", content="v1"))
        entry.push("staging", PromptVersion(version="v2", content="v2"))
        entry.environments["production"] = "v2"
        entry.rollback("production", "v1")
        assert entry.environments["production"] == "v1"

    def test_rollback_missing(self):
        entry = PromptEntry(name="test:prompt")
        import pytest

        with pytest.raises(ValueError, match="not found"):
            entry.rollback("production", "nonexistent")

    def test_ab_test_lifecycle(self):
        entry = PromptEntry(name="test:prompt")
        entry.push("staging", PromptVersion(version="v1", content="v1"))
        entry.push("staging", PromptVersion(version="v2", content="v2"))
        entry.environments["production"] = "v1"

        variants = [
            ABVariant(version="v2", weight=0.1, description="new"),
            ABVariant(version="v1", weight=0.9, description="control"),
        ]
        cfg = entry.start_ab_test(variants, control="v1")
        assert cfg.status == ABTestStatus.RUNNING
        assert len(entry.ab_tests) == 1

        entry.stop_ab_test(cfg.id, winner="v2")
        assert entry.environments["production"] == "v2"
        assert entry.ab_tests[0].status == ABTestStatus.PROMOTED

    def test_version_history(self):
        entry = PromptEntry(name="test:prompt")
        entry.push("staging", PromptVersion(version="v1", content="v1"))
        entry.push("staging", PromptVersion(version="v2", content="v2"))
        assert entry.version_history() == ["v1", "v2"]
        assert entry.latest_version().version == "v2"
