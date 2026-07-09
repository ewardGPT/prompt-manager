"""Core Pydantic schema for prompt management.

Prompts are versioned assets with content hashing, environment mapping,
and A/B test configuration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256

from pydantic import BaseModel, Field


class Environment(str, Enum):
    STAGING = "staging"
    PRODUCTION = "production"
    DEVELOPMENT = "development"


class ABTestStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"


class PromptVersion(BaseModel):
    """A single version of a prompt, with content and metadata."""

    version: str
    hash: str = ""
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    template_vars: dict[str, str] = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

    def compute_hash(self) -> str:
        """Compute SHA256 hash of prompt content."""
        self.hash = sha256(self.content.encode()).hexdigest()[:12]
        return self.hash

    def model_post_init(self, __context) -> None:
        if not self.hash:
            self.compute_hash()


class ABVariant(BaseModel):
    """A named variant with a traffic weight."""

    version: str
    weight: float  # 0.0 to 1.0
    description: str = ""


class ABTestConfig(BaseModel):
    """A/B test configuration for a prompt."""

    id: str
    status: ABTestStatus = ABTestStatus.RUNNING
    variants: list[ABVariant] = Field(default_factory=list)
    control_version: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)

    def weight_sum(self) -> float:
        return sum(v.weight for v in self.variants)

    def is_valid(self) -> bool:
        return abs(self.weight_sum() - 1.0) < 0.001


class PromptEntry(BaseModel):
    """A named prompt with its version history and environment assignments."""

    # Identity: "agentic-inbox:draft-reply" format
    name: str
    description: str = ""

    # Current version per environment
    environments: dict[str, str] = Field(
        default_factory=dict, description="env → version, e.g. staging → v3, production → v2"
    )

    # Full version history
    versions: list[PromptVersion] = Field(default_factory=list)

    # Active A/B tests
    ab_tests: list[ABTestConfig] = Field(default_factory=list)

    # Eval gate requirements
    eval_suite: str = ""  # suite name to run before promotion

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def current_version(self, env: str) -> str | None:
        return self.environments.get(env)

    def version_history(self) -> list[str]:
        return [v.version for v in self.versions]

    def get_version(self, version: str) -> PromptVersion | None:
        for v in self.versions:
            if v.version == version:
                return v
        return None

    def latest_version(self) -> PromptVersion | None:
        return self.versions[-1] if self.versions else None

    def push(self, env: str, version: PromptVersion) -> PromptVersion:
        """Push a version to an environment. Adds to history if new."""
        existing = self.get_version(version.version)
        if existing:
            existing.content = version.content
            existing.compute_hash()
            existing.created_at = datetime.now(timezone.utc)
        else:
            self.versions.append(version)

        self.environments[env] = version.version
        self.updated_at = datetime.now(timezone.utc)
        return version

    def rollback(self, env: str, to_version: str) -> str:
        """Rollback an environment to a previous version."""
        if to_version not in self.version_history():
            available = ", ".join(self.version_history())
            raise ValueError(f"Version '{to_version}' not found. Available: {available}")
        self.environments[env] = to_version
        self.updated_at = datetime.now(timezone.utc)
        return to_version

    def start_ab_test(self, variants: list[ABVariant], control: str) -> ABTestConfig:
        """Start an A/B test with weighted variants."""
        test_id = f"ab-{len(self.ab_tests) + 1}"
        config = ABTestConfig(
            id=test_id,
            variants=variants,
            control_version=control,
        )
        self.ab_tests.append(config)
        self.updated_at = datetime.now(timezone.utc)
        return config

    def stop_ab_test(self, test_id: str, *, winner: str | None = None) -> ABTestConfig:
        """Stop an A/B test, optionally promoting a winner."""
        for t in self.ab_tests:
            if t.id == test_id and t.status == ABTestStatus.RUNNING:
                t.status = ABTestStatus.PROMOTED if winner else ABTestStatus.STOPPED
                t.ended_at = datetime.now(timezone.utc)
                if winner:
                    self.environments["production"] = winner
                self.updated_at = datetime.now(timezone.utc)
                return t
        raise KeyError(f"No running A/B test with id '{test_id}'")


class PromptStoreIndex(BaseModel):
    """Index mapping prompt names to their file paths."""

    version: str = "1.0"
    prompts: dict[str, str] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
