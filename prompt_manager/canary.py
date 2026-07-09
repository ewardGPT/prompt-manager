"""Canary deployer for prompt-manager.

Gradual rollout: push to N% → monitor → auto-decide promote/rollback.
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone

from prompt_manager.storage import PromptStore


class CanaryState:
    def __init__(
        self,
        prompt_name: str,
        canary_version: str,
        control_version: str,
        weight: float = 0.10,
        env: str = "production",
    ) -> None:
        self.prompt_name = prompt_name
        self.canary_version = canary_version
        self.control_version = control_version
        self.weight = weight
        self.env = env
        self.started_at = datetime.now(timezone.utc)
        self.phase = "running"
        self.check_count = 0


def canary_deploy(
    store: PromptStore,
    prompt_name: str,
    canary_version: str,
    control_version: str,
    weight: float = 0.10,
) -> CanaryState:
    """Start a canary deployment of a prompt version."""
    from prompt_manager.schema import ABVariant

    entry = store.get(prompt_name)
    entry.start_ab_test(
        [
            ABVariant(version=canary_version, weight=weight, description="canary"),
            ABVariant(version=control_version, weight=1 - weight, description="control"),
        ],
        control=control_version,
    )
    store.put(entry)

    return CanaryState(
        prompt_name=prompt_name,
        canary_version=canary_version,
        control_version=control_version,
        weight=weight,
    )


def canary_decide(
    store: PromptStore,
    prompt_name: str,
    metric_check: str = "error_rate < 0.05",
    required_checks: int = 3,
    check_interval_sec: float = 60,
) -> dict:
    """Monitor telemetry and auto-decide: promote or rollback.

    Runs `agent-telemetry alert` repeatedly until confidence threshold reached.
    """
    entry = store.get(prompt_name)
    running = [t for t in entry.ab_tests if t.status.value == "running"]
    if not running:
        return {"decision": "no_active_canary", "reason": "No running A/B test"}

    test = running[0]
    canary_ver = next((v.version for v in test.variants if v.weight > 0 and v.weight < 1), None)
    if not canary_ver:
        return {"decision": "unknown", "reason": "No canary variant found"}

    checks_passed = 0
    for i in range(required_checks):
        result = subprocess.run(
            ["agent-telemetry", "alert", metric_check, "--agent", prompt_name.split(":")[0]],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            checks_passed += 1

        if i < required_checks - 1:
            time.sleep(check_interval_sec)

    confidence = checks_passed / required_checks
    if confidence >= 0.8:
        entry.stop_ab_test(test.id, winner=canary_ver)
        store.put(entry)
        return {"decision": "promoted", "version": canary_ver, "confidence": confidence}

    entry.stop_ab_test(test.id)
    store.put(entry)
    return {
        "decision": "rolled_back",
        "version": canary_ver,
        "confidence": confidence,
        "reason": "Checks failed",
    }
