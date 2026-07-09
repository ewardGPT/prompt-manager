# Prompt Manager

Version-controlled prompt management with staged rollouts, A/B testing, and rollbacks. Change prompts without deploying code.

## Quick Start

```bash
pip install -e .

# Push a new prompt version to staging
prompt-manager push agentic-inbox:draft-reply --file prompt.txt --version v4 --env staging

# Pull the current production prompt
prompt-manager pull agentic-inbox:draft-reply --env production

# List all managed prompts
prompt-manager list
prompt-manager list --env staging

# Get full details with version history
prompt-manager get agentic-inbox:draft-reply

# Diff two versions
prompt-manager diff agentic-inbox:draft-reply --v1 v3 --v2 v4

# Promote from staging to production
prompt-manager promote agentic-inbox:draft-reply --from staging --to production

# Emergency rollback
prompt-manager rollback agentic-inbox:draft-reply --to v3 --env production

# Start A/B test (10% v4, 90% v3)
prompt-manager ab-test start agentic-inbox:draft-reply --variants v4:10,v3:90 --control v3

# Stop A/B test and pick winner
prompt-manager ab-test stop agentic-inbox:draft-reply --test-id ab-1 --winner v4
```

## CLI Reference

| Command | Description |
|---|---|
| `push <name> --file <path> --version <v> [--env e]` | Push prompt to an environment |
| `pull <name> [--env e]` | Pull current prompt content |
| `list [--env e]` | List all managed prompts |
| `get <name>` | Show full prompt details and history |
| `diff <name> --v1 X --v2 Y` | Compare two versions |
| `rollback <name> --to <v> [--env e]` | Rollback to a previous version |
| `promote <name> --from X --to Y` | Promote between environments |
| `validate <name> [--env e]` | Validate against eval suite |
| `ab-test start <name> --variants v:W,... --control v` | Start A/B test |
| `ab-test stop <name> --test-id X [--winner v]` | Stop A/B test |
| `ab-test list [--name n]` | List running tests |
| `config <name> [--eval-suite X]` | Configure prompt settings |

## How It Works

Prompts are versioned assets stored as YAML files in `~/.config/prompt-manager/prompts/`. Set `PROMPT_MANAGER_DIR` to override.

Each prompt entry tracks:
- **Versions** — full history with content hashes
- **Environments** — which version is active in staging vs production
- **A/B tests** — weighted traffic splits between versions
- **Eval suites** — validation gate before promotion

No database. Git-ops friendly. Rollbacks are instant (just pointer updates, no redeploy).

## Integration with Eval Harness

Configure an eval suite and the `validate` command will gate promotions:

```bash
prompt-manager config agentic-inbox:draft-reply --eval-suite agentic_inbox:auto_draft
prompt-manager validate agentic-inbox:draft-reply --env staging
```

Full eval-harness integration (auto-trigger on promote) coming in v0.2.0.
