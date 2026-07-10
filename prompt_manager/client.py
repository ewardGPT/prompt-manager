"""PromptsClient — SDK entry point for Prompt Manager.

Pattern: env-var fallback, @cached_property resource hierarchy, sync/async mirror.

Usage:
    from prompt_manager import PromptsClient

    client = PromptsClient()
    for entry in client.prompts.list():
        print(entry.name)

    content = client.prompts.get("agentic-inbox:draft-reply")
    client.prompts.set("agentic-inbox:draft-reply", "new content", env="staging")
    client.versions.list("agentic-inbox:draft-reply")
    client.diff.compare("agentic-inbox:draft-reply", "v1", "v2")
"""

from __future__ import annotations

import os
from functools import cached_property
from typing import Any

from prompt_manager.schema import PromptEntry, PromptVersion
from prompt_manager.storage import PromptStore


def _make_store(*, config_dir: str | None = None) -> PromptStore:
    resolved = (
        config_dir or os.environ.get("PROMPT_CONFIG_DIR") or os.environ.get("PROMPT_MANAGER_DIR")
    )
    return PromptStore(root=resolved) if resolved else PromptStore()


# ── Resources ───────────────────────────────────────────────────────────


class PromptsResource:
    """CRUD for prompt entries."""

    def __init__(self, store: PromptStore, default_env: str) -> None:
        self._store = store
        self._default_env = default_env

    def list(self, env: str | None = None) -> list[PromptEntry]:
        """List all prompts, optionally filtered by environment."""
        prompts = self._store.list_all()
        if env:
            return [p for p in prompts if env in p.environments]
        return prompts

    def get(self, name: str, env: str | None = None) -> PromptEntry:
        """Get a prompt entry by name. If env is set, raises if not deployed there."""
        entry = self._store.get(name)
        if env is not None and env not in entry.environments:
            raise KeyError(f"Prompt '{name}' has no version in environment '{env}'")
        return entry

    def search(self, text: str) -> list[PromptEntry]:
        """Find prompts whose content contains text (case-insensitive)."""
        results: list[PromptEntry] = []
        lower = text.lower()
        for entry in self._store.list_all():
            for v in entry.versions:
                if lower in v.content.lower():
                    results.append(entry)
                    break
        return results

    def set(
        self,
        name: str,
        content: str,
        env: str | None = None,
        version: str | None = None,
        description: str = "",
    ) -> PromptEntry:
        """Push a new version to an environment. Auto-generates version label if omitted."""
        pv = PromptVersion(
            version=version or _next_version(self._store, name),
            content=content,
        )
        pv.compute_hash()
        if description:
            pv.metadata["description"] = description
        return self._store.push_version(name, env or self._default_env, pv)


class DiffResource:
    """Compare prompt versions."""

    def __init__(self, store: PromptStore, default_env: str) -> None:
        self._store = store
        self._default_env = default_env

    def compare(self, name: str, v1: str, v2: str) -> dict[str, Any]:
        """Compare two versions of a prompt."""
        entry = self._store.get(name)
        pv1 = entry.get_version(v1)
        pv2 = entry.get_version(v2)
        if not pv1:
            raise KeyError(f"Version '{v1}' not found for '{name}'")
        if not pv2:
            raise KeyError(f"Version '{v2}' not found for '{name}'")
        return {
            "name": name,
            "v1": pv1,
            "v2": pv2,
            "identical": pv1.content == pv2.content,
        }

    def since(self, name: str, version: str) -> dict[str, Any]:
        """Compare current environment version against a historical version."""
        entry = self._store.get(name)
        current_ver = entry.current_version(self._default_env)
        if not current_ver:
            raise ValueError(f"No version assigned to '{self._default_env}' for '{name}'")
        return self.compare(name, version, current_ver)

    def env_diff(
        self, name: str, env1: str | None = None, env2: str | None = None
    ) -> dict[str, Any]:
        """Compare content between two environments."""
        e1 = env1 or self._default_env
        e2 = env2 or "production"
        entry = self._store.get(name)
        v1 = entry.current_version(e1)
        v2 = entry.current_version(e2)
        if not v1:
            raise ValueError(f"No version in '{e1}' for '{name}'")
        if not v2:
            raise ValueError(f"No version in '{e2}' for '{name}'")
        return self.compare(name, v1, v2)


class VersionsResource:
    """Version history management."""

    def __init__(self, store: PromptStore, default_env: str) -> None:
        self._store = store
        self._default_env = default_env

    def list(self, name: str) -> list[PromptVersion]:
        """List all versions for a prompt."""
        return self._store.get(name).versions

    def get(self, name: str, version: str) -> PromptVersion:
        """Get a specific version by label."""
        pv = self._store.get(name).get_version(version)
        if not pv:
            raise KeyError(f"Version '{version}' not found for '{name}'")
        return pv

    def promote(self, name: str, version: str, to_env: str) -> PromptEntry:
        """Assign a specific version to an environment (promote)."""
        entry = self._store.get(name)
        if not entry.get_version(version):
            raise KeyError(f"Version '{version}' not found in history for '{name}'")
        entry.environments[to_env] = version
        from datetime import datetime, timezone

        entry.updated_at = datetime.now(timezone.utc)
        return self._store.put(entry)

    def promote_from_env(self, name: str, from_env: str, to_env: str) -> PromptEntry:
        """Promote the current version of one environment to another."""
        entry = self._store.get(name)
        version = entry.current_version(from_env)
        if not version:
            raise ValueError(f"No version in '{from_env}' for '{name}'")
        return self.promote(name, version, to_env)


# ── Helpers ─────────────────────────────────────────────────────────────


def _next_version(store: PromptStore, name: str) -> str:
    """Generate the next version label (v1, v2, ...) for a prompt."""
    try:
        entry = store.get(name)
        existing = [v.version for v in entry.versions]
    except (KeyError, FileNotFoundError):
        existing = []

    nums = []
    for v in existing:
        if v.startswith("v") and v[1:].isdigit():
            nums.append(int(v[1:]))
    return f"v{max(nums) + 1}" if nums else "v1"


# ── PromptsClient (sync) ────────────────────────────────────────────────


class PromptsClient:
    """Prompt Manager Python SDK entry point.

    One import, one object, everything discoverable from there.
    """

    env: str
    config_dir: str | None
    _store: PromptStore

    def __init__(
        self,
        *,
        env: str | None = None,
        config_dir: str | None = None,
    ) -> None:
        self.env = env or os.environ.get("PROMPT_ENV", "production")
        self.config_dir = config_dir
        self._store = _make_store(config_dir=config_dir)

    @cached_property
    def prompts(self) -> PromptsResource:
        return PromptsResource(self._store, self.env)

    @cached_property
    def diff(self) -> DiffResource:
        return DiffResource(self._store, self.env)

    @cached_property
    def versions(self) -> VersionsResource:
        return VersionsResource(self._store, self.env)


# ── AsyncPromptsClient (async mirror) ───────────────────────────────────


class AsyncPromptsClient:
    """Async mirror of PromptsClient.

    Same interface, all methods async via asyncio.to_thread.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._sync = PromptsClient(**kwargs)
        self.env = self._sync.env
        self.config_dir = self._sync.config_dir

    @cached_property
    def prompts(self) -> PromptsResource:
        return self._sync.prompts

    @cached_property
    def diff(self) -> DiffResource:
        return self._sync.diff

    @cached_property
    def versions(self) -> VersionsResource:
        return self._sync.versions

    async def _run(self, method, *args, **kwargs):
        import asyncio

        return await asyncio.to_thread(method, *args, **kwargs)

    async def list(self, **kwargs: Any) -> list[PromptEntry]:
        return await self._run(self._sync.prompts.list, **kwargs)

    async def get(self, **kwargs: Any) -> PromptEntry:
        return await self._run(self._sync.prompts.get, **kwargs)

    async def search(self, **kwargs: Any) -> list[PromptEntry]:
        return await self._run(self._sync.prompts.search, **kwargs)

    async def set(self, **kwargs: Any) -> PromptEntry:
        return await self._run(self._sync.prompts.set, **kwargs)
