"""Filesystem-based storage for prompt entries.

Each prompt is a YAML file in ~/.config/prompt-manager/prompts/.
Version history is embedded in the entry file. Git-ops ready.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from prompt_manager.schema import PromptEntry, PromptStoreIndex, PromptVersion


class PromptStore:
    """Read/write prompt entries to a filesystem directory."""

    DEFAULT_DIR = Path.home() / ".config" / "prompt-manager" / "prompts"

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else self.DEFAULT_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / "index.yaml"

    # ── Index ──────────────────────────────────────────────────────────────

    def index(self) -> PromptStoreIndex:
        if not self._index_path.exists():
            return PromptStoreIndex()
        data = yaml.safe_load(self._index_path.read_text()) or {}
        return PromptStoreIndex(**data)

    def _save_index(self, idx: PromptStoreIndex) -> None:
        idx.generated_at = datetime.now(timezone.utc)
        self._index_path.write_text(
            yaml.dump(idx.model_dump(mode="json", exclude_none=True), sort_keys=False)
        )

    # ── CRUD ───────────────────────────────────────────────────────────────

    def get(self, name: str) -> PromptEntry:
        """Retrieve a prompt entry by name (e.g. 'agentic-inbox:draft-reply')."""
        idx = self.index()
        if name not in idx.prompts:
            raise KeyError(f"Prompt '{name}' not found. Available: {list(idx.prompts)}")
        path = self.root / idx.prompts[name]
        if not path.exists():
            raise FileNotFoundError(f"Prompt file missing: {path}")
        return _parse(path)

    def put(self, entry: PromptEntry) -> PromptEntry:
        """Save or update a prompt entry."""
        entry.updated_at = datetime.now(timezone.utc)
        filename = _safe_filename(entry.name) + ".yaml"
        path = self.root / filename
        _write(path, entry)

        idx = self.index()
        idx.prompts[entry.name] = filename
        self._save_index(idx)
        return entry

    def list_all(self) -> list[PromptEntry]:
        idx = self.index()
        result: list[PromptEntry] = []
        for relpath in idx.prompts.values():
            path = self.root / relpath
            if path.exists():
                result.append(_parse(path))
        return result

    def push_version(self, name: str, env: str, version: PromptVersion) -> PromptEntry:
        """Push a new prompt version to an environment."""
        try:
            entry = self.get(name)
        except (KeyError, FileNotFoundError):
            entry = PromptEntry(name=name)

        entry.push(env, version)
        return self.put(entry)

    def pull_version(self, name: str, env: str) -> PromptVersion | str:
        """Pull the current prompt version from an environment. Returns content."""
        entry = self.get(name)
        ver = entry.current_version(env)
        if not ver:
            raise ValueError(f"No version assigned to '{env}' for '{name}'")
        pv = entry.get_version(ver)
        if not pv:
            raise ValueError(f"Version '{ver}' not found in history")
        return pv.content

    def rollback(self, name: str, env: str, to_version: str) -> str:
        """Rollback an environment to a specific version."""
        entry = self.get(name)
        entry.rollback(env, to_version)
        self.put(entry)
        return to_version

    def start_ab_test(self, name: str, variants: list, control: str) -> PromptEntry:
        """Start an A/B test on a prompt."""
        entry = self.get(name)
        entry.start_ab_test(variants, control)
        return self.put(entry)

    def stop_ab_test(self, name: str, test_id: str, *, winner: str | None = None) -> PromptEntry:
        """Stop an A/B test, optionally with a winner."""
        entry = self.get(name)
        entry.stop_ab_test(test_id, winner=winner)
        return self.put(entry)


def _parse(path: Path) -> PromptEntry:
    raw = yaml.safe_load(path.read_text())
    if raw is None:
        raise ValueError(f"Empty YAML: {path}")
    return PromptEntry(**raw)


def _write(path: Path, entry: PromptEntry) -> None:
    data = entry.model_dump(mode="json", exclude_none=True)
    path.write_text(yaml.dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True))


def _safe_filename(name: str) -> str:
    return name.replace(":", "-").replace("/", "-").replace(" ", "-")
