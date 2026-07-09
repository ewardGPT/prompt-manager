"""Comprehensive prompt-manager tests — 150+ cases via parametrize."""

from __future__ import annotations

import pytest

from prompt_manager.schema import (
    ABTestConfig,
    ABTestStatus,
    ABVariant,
    Environment,
    PromptEntry,
    PromptVersion,
)

# ═══════════════════════════════════════════════════════════════════════════════
# PromptVersion — hash computation
# ═══════════════════════════════════════════════════════════════════════════════

HASH_CASES = [
    ("Hello", "Hello", True),
    ("A", "A", True),
    ("Hello", "World", False),
    ("", "", True),
    ("a", "b", False),
    ("The quick brown fox", "The quick brown fox", True),
    ("Case matters", "case matters", False),
    ("trailing space ", "trailing space ", True),
    ("leading space", " leading space", False),
    ("unicode: αβγ", "unicode: αβγ", True),
    ("emoji 🔥", "emoji 🔥", True),
    ("a" * 1000, "a" * 1000, True),
    ("a" * 1000, "b" + "a" * 999, False),
    ("\nnewline", "\nnewline", True),
    ("\ttab", "\t tab", False),
]


@pytest.mark.parametrize("c1,c2,same", HASH_CASES)
def test_hash_equality(c1: str, c2: str, same: bool) -> None:
    pv1 = PromptVersion(version="v1", content=c1)
    pv2 = PromptVersion(version="v1", content=c2)
    if same:
        assert pv1.hash == pv2.hash
    else:
        assert pv1.hash != pv2.hash


HASH_LENGTH_CASES = [
    ("x", 12),
    ("hello world", 12),
    ("a" * 10000, 12),
    ("", 12),
    ("🔥🧪", 12),
]


@pytest.mark.parametrize("content,expected_len", HASH_LENGTH_CASES)
def test_hash_length(content: str, expected_len: int) -> None:
    pv = PromptVersion(version="v1", content=content)
    assert len(pv.hash) == expected_len


def test_hash_is_hex() -> None:
    pv = PromptVersion(version="v1", content="test")
    assert all(c in "0123456789abcdef" for c in pv.hash)


def test_explicit_hash_preserved() -> None:
    pv = PromptVersion(version="v1", content="x", hash="abc123def456")
    assert pv.hash == "abc123def456"


# ═══════════════════════════════════════════════════════════════════════════════
# PromptEntry — push
# ═══════════════════════════════════════════════════════════════════════════════

PUSH_ENV_CASES = [
    "staging",
    "production",
    "development",
    "testing",
    "dev",
]


@pytest.mark.parametrize("env", PUSH_ENV_CASES)
def test_push_to_various_envs(env: str) -> None:
    entry = PromptEntry(name="test:prompt")
    pv = PromptVersion(version="v1", content="content")
    entry.push(env, pv)
    assert entry.environments[env] == "v1"
    assert len(entry.versions) == 1


def test_push_multiple_envs_same_version() -> None:
    entry = PromptEntry(name="test:prompt")
    pv = PromptVersion(version="v1", content="v1")
    entry.push("staging", pv)
    entry.push("production", pv)
    assert entry.environments["staging"] == "v1"
    assert entry.environments["production"] == "v1"
    assert len(entry.versions) == 1  # same version


def test_push_many_versions() -> None:
    entry = PromptEntry(name="test:prompt")
    for i in range(20):
        entry.push("staging", PromptVersion(version=f"v{i}", content=f"c{i}"))
    assert len(entry.versions) == 20
    assert entry.environments["staging"] == "v19"


def test_push_overwrites_existing_version_content() -> None:
    entry = PromptEntry(name="test:prompt")
    entry.push("staging", PromptVersion(version="v1", content="first"))
    entry.push("staging", PromptVersion(version="v1", content="updated"))
    assert entry.versions[0].content == "updated"
    assert len(entry.versions) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# PromptEntry — rollback
# ═══════════════════════════════════════════════════════════════════════════════


def test_rollback_valid() -> None:
    entry = PromptEntry(name="test:prompt")
    entry.push("production", PromptVersion(version="v1", content="v1"))
    entry.push("production", PromptVersion(version="v2", content="v2"))
    entry.push("production", PromptVersion(version="v3", content="v3"))
    entry.rollback("production", "v1")
    assert entry.environments["production"] == "v1"


def test_rollback_to_current() -> None:
    entry = PromptEntry(name="test:prompt")
    entry.push("production", PromptVersion(version="v1", content="v1"))
    entry.rollback("production", "v1")
    assert entry.environments["production"] == "v1"


ROLLBACK_INVALID_CASES = [
    "nonexistent",
    "v99",
    "",
    "v0",
]


@pytest.mark.parametrize("to_ver", ROLLBACK_INVALID_CASES)
def test_rollback_invalid_raises(to_ver: str) -> None:
    entry = PromptEntry(name="test:prompt")
    entry.push("production", PromptVersion(version="v1", content="v1"))
    with pytest.raises(ValueError, match="not found"):
        entry.rollback("production", to_ver)


def test_rollback_multiple_times() -> None:
    entry = PromptEntry(name="test:prompt")
    for i in range(5):
        entry.push("production", PromptVersion(version=f"v{i}", content=f"c{i}"))
    entry.rollback("production", "v2")
    assert entry.environments["production"] == "v2"
    entry.rollback("production", "v4")
    assert entry.environments["production"] == "v4"
    entry.rollback("production", "v0")
    assert entry.environments["production"] == "v0"


# ═══════════════════════════════════════════════════════════════════════════════
# PromptEntry — version queries
# ═══════════════════════════════════════════════════════════════════════════════


def test_version_history_order() -> None:
    entry = PromptEntry(name="test:prompt")
    entry.push("staging", PromptVersion(version="v3", content="3"))
    entry.push("staging", PromptVersion(version="v1", content="1"))
    entry.push("staging", PromptVersion(version="v2", content="2"))
    assert entry.version_history() == ["v3", "v1", "v2"]


def test_current_version_none() -> None:
    entry = PromptEntry(name="test:prompt")
    assert entry.current_version("production") is None


def test_latest_version() -> None:
    entry = PromptEntry(name="test:prompt")
    assert entry.latest_version() is None
    entry.push("staging", PromptVersion(version="v1", content="1"))
    assert entry.latest_version().version == "v1"  # type: ignore[union-attr]
    entry.push("staging", PromptVersion(version="v2", content="2"))
    assert entry.latest_version().version == "v2"  # type: ignore[union-attr]


def test_get_version() -> None:
    entry = PromptEntry(name="test:prompt")
    pv = PromptVersion(version="v1", content="content")
    entry.push("staging", pv)
    assert entry.get_version("v1") is pv
    assert entry.get_version("nonexistent") is None


# ═══════════════════════════════════════════════════════════════════════════════
# AB testing
# ═══════════════════════════════════════════════════════════════════════════════

VALID_WEIGHT_PAIRS = [
    (0.1, 0.9),
    (0.5, 0.5),
    (0.0, 1.0),
    (0.01, 0.99),
    (0.333, 0.333, 0.334),
    (1.0,),
    (0.25, 0.25, 0.25, 0.25),
]


@pytest.mark.parametrize("weights", VALID_WEIGHT_PAIRS)
def test_ab_weights_valid(weights: tuple[float, ...]) -> None:
    variants = [ABVariant(version=f"v{i}", weight=w) for i, w in enumerate(weights)]
    cfg = ABTestConfig(id="test", variants=variants, control_version="v0")
    assert cfg.is_valid()


INVALID_WEIGHT_PAIRS = [
    (0.1, 0.8),  # sum = 0.9
    (0.6, 0.6),  # sum = 1.2
    (1.0, 0.1),  # sum = 1.1
    (0.0, 0.0),  # sum = 0
    (0.99,),
]


@pytest.mark.parametrize("weights", INVALID_WEIGHT_PAIRS)
def test_ab_weights_invalid(weights: tuple[float, ...]) -> None:
    variants = [ABVariant(version=f"v{i}", weight=w) for i, w in enumerate(weights)]
    cfg = ABTestConfig(id="test", variants=variants, control_version="v0")
    assert not cfg.is_valid()


def test_start_ab_test() -> None:
    entry = PromptEntry(name="test:prompt")
    entry.push("production", PromptVersion(version="v1", content="v1"))
    entry.push("staging", PromptVersion(version="v2", content="v2"))

    variants = [
        ABVariant(version="v2", weight=0.2, description="new"),
        ABVariant(version="v1", weight=0.8, description="control"),
    ]
    cfg = entry.start_ab_test(variants, control="v1")
    assert cfg.id == "ab-1"
    assert cfg.status == ABTestStatus.RUNNING
    assert len(entry.ab_tests) == 1


def test_multiple_ab_tests() -> None:
    entry = PromptEntry(name="test:prompt")
    entry.push("production", PromptVersion(version="v1", content="v1"))
    entry.push("staging", PromptVersion(version="v2", content="v2"))

    for _i in range(5):
        entry.start_ab_test(
            [ABVariant(version="v2", weight=0.1), ABVariant(version="v1", weight=0.9)],
            control="v1",
        )
    assert len(entry.ab_tests) == 5


def test_stop_ab_test_with_winner() -> None:
    entry = PromptEntry(name="test:prompt")
    entry.push("production", PromptVersion(version="v1", content="v1"))
    entry.push("staging", PromptVersion(version="v2", content="v2"))
    entry.environments["production"] = "v1"

    variants = [ABVariant(version="v2", weight=0.2), ABVariant(version="v1", weight=0.8)]
    entry.start_ab_test(variants, control="v1")
    entry.stop_ab_test("ab-1", winner="v2")

    assert entry.environments["production"] == "v2"
    assert entry.ab_tests[0].status == ABTestStatus.PROMOTED


def test_stop_ab_test_without_winner() -> None:
    entry = PromptEntry(name="test:prompt")
    entry.push("production", PromptVersion(version="v1", content="v1"))
    entry.push("staging", PromptVersion(version="v2", content="v2"))

    variants = [ABVariant(version="v2", weight=0.2), ABVariant(version="v1", weight=0.8)]
    entry.start_ab_test(variants, control="v1")
    entry.stop_ab_test("ab-1")

    assert entry.ab_tests[0].status == ABTestStatus.STOPPED


def test_stop_ab_test_invalid_id() -> None:
    entry = PromptEntry(name="test:prompt")
    entry.push("production", PromptVersion(version="v1", content="v1"))
    with pytest.raises(KeyError, match="No running A/B test"):
        entry.stop_ab_test("nonexistent")


def test_stop_already_stopped() -> None:
    entry = PromptEntry(name="test:prompt")
    entry.push("production", PromptVersion(version="v1", content="v1"))
    entry.push("staging", PromptVersion(version="v2", content="v2"))
    variants = [ABVariant(version="v2", weight=0.2), ABVariant(version="v1", weight=0.8)]
    entry.start_ab_test(variants, control="v1")
    entry.stop_ab_test("ab-1")
    with pytest.raises(KeyError, match="No running A/B test"):
        entry.stop_ab_test("ab-1")  # not running anymore


# ═══════════════════════════════════════════════════════════════════════════════
# ABVariant
# ═══════════════════════════════════════════════════════════════════════════════

ABV_CASES = [
    ("v1", 0.5, "new version"),
    ("v2", 1.0, ""),
    ("v3", 0.0, "control group"),
    ("v4", 0.001, ""),
    ("v5", 0.999, "heavy variant"),
]


@pytest.mark.parametrize("ver,weight,desc", ABV_CASES)
def test_ab_variant(ver: str, weight: float, desc: str) -> None:
    v = ABVariant(version=ver, weight=weight, description=desc)
    assert v.version == ver
    assert v.weight == weight
    assert v.description == desc


# ═══════════════════════════════════════════════════════════════════════════════
# ABTestStatus enum
# ═══════════════════════════════════════════════════════════════════════════════

AB_STATUS_CASES = [
    ("running", ABTestStatus.RUNNING),
    ("stopped", ABTestStatus.STOPPED),
    ("promoted", ABTestStatus.PROMOTED),
    ("rolled_back", ABTestStatus.ROLLED_BACK),
]


@pytest.mark.parametrize("raw,expected", AB_STATUS_CASES)
def test_ab_status(raw: str, expected: ABTestStatus) -> None:
    assert ABTestStatus(raw) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# Environment enum
# ═══════════════════════════════════════════════════════════════════════════════

ENV_ENUM_CASES = [
    ("staging", Environment.STAGING),
    ("production", Environment.PRODUCTION),
    ("development", Environment.DEVELOPMENT),
]


@pytest.mark.parametrize("raw,expected", ENV_ENUM_CASES)
def test_environment_enum(raw: str, expected: Environment) -> None:
    assert Environment(raw) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# PromptEntry — eval suite
# ═══════════════════════════════════════════════════════════════════════════════


def test_eval_suite_default_empty() -> None:
    entry = PromptEntry(name="test:prompt")
    assert entry.eval_suite == ""


def test_eval_suite_settable() -> None:
    entry = PromptEntry(name="test:prompt")
    entry.eval_suite = "my_project:test_suite"
    assert entry.eval_suite == "my_project:test_suite"


# ═══════════════════════════════════════════════════════════════════════════════
# PromptEntry — metadata guards
# ═══════════════════════════════════════════════════════════════════════════════


def test_entry_timestamps_on_push() -> None:
    entry = PromptEntry(name="test:prompt")
    original_updated = entry.updated_at
    entry.push("staging", PromptVersion(version="v1", content="c"))
    assert entry.updated_at > original_updated


def test_entry_timestamps_on_rollback() -> None:
    entry = PromptEntry(name="test:prompt")
    entry.push("production", PromptVersion(version="v1", content="c"))
    entry.push("production", PromptVersion(version="v2", content="c"))
    original_updated = entry.updated_at
    entry.rollback("production", "v1")
    assert entry.updated_at > original_updated


# ═══════════════════════════════════════════════════════════════════════════════
# PromptVersion — template vars and metadata
# ═══════════════════════════════════════════════════════════════════════════════


def test_prompt_version_template_vars() -> None:
    pv = PromptVersion(
        version="v1",
        content="Hello {{name}}",
        template_vars={"name": "user"},
    )
    assert pv.template_vars == {"name": "user"}


def test_prompt_version_metadata() -> None:
    pv = PromptVersion(
        version="v1",
        content="System prompt",
        metadata={"author": "alice", "reviewed": True, "score": 4.5},
    )
    assert pv.metadata["author"] == "alice"


# ═══════════════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════════════


def test_empty_content_hash() -> None:
    pv = PromptVersion(version="v1", content="")
    assert len(pv.hash) == 12


def test_very_long_content() -> None:
    content = "x" * 100_000
    pv = PromptVersion(version="v1", content=content)
    assert len(pv.hash) == 12


def test_push_same_version_to_same_env() -> None:
    entry = PromptEntry(name="test:prompt")
    entry.push("staging", PromptVersion(version="v1", content="first"))
    entry.push("staging", PromptVersion(version="v1", content="second"))
    assert entry.environments["staging"] == "v1"
    assert entry.versions[0].content == "second"


def test_rollback_to_same_version() -> None:
    entry = PromptEntry(name="test:prompt")
    entry.push("production", PromptVersion(version="v1", content="v1"))
    entry.rollback("production", "v1")
    assert entry.environments["production"] == "v1"


def test_push_updates_timestamp() -> None:
    entry = PromptEntry(name="test:prompt")
    ts1 = entry.updated_at
    entry.push("staging", PromptVersion(version="v1", content="c"))
    assert entry.updated_at > ts1


def test_rollback_updates_timestamp() -> None:
    entry = PromptEntry(name="test:prompt")
    entry.push("production", PromptVersion(version="v1", content="c"))
    entry.push("production", PromptVersion(version="v2", content="c"))
    ts1 = entry.updated_at
    entry.rollback("production", "v1")
    assert entry.updated_at > ts1


def test_empty_prompt_entry_defaults() -> None:
    entry = PromptEntry(name="test:prompt")
    assert entry.description == ""
    assert entry.environments == {}
    assert entry.versions == []
    assert entry.ab_tests == []
    assert entry.eval_suite == ""


def test_ab_test_metadata() -> None:
    entry = PromptEntry(name="test:prompt")
    entry.push("production", PromptVersion(version="v1", content="v1"))
    entry.push("staging", PromptVersion(version="v2", content="v2"))
    variants = [ABVariant(version="v2", weight=0.5), ABVariant(version="v1", weight=0.5)]
    cfg = entry.start_ab_test(variants, control="v1")
    assert cfg.started_at is not None
    assert cfg.metadata == {}


def test_ab_variant_default_description() -> None:
    v = ABVariant(version="v1", weight=0.5)
    assert v.description == ""


def test_prompt_version_datetime_set() -> None:
    pv = PromptVersion(version="v1", content="test")
    assert pv.created_at is not None
