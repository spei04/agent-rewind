# Agent Rewind

**Find the decision worth changing. Measure whether the change holds up.**

[![checks](https://github.com/spei04/agent-rewind/actions/workflows/ci.yml/badge.svg)](https://github.com/spei04/agent-rewind/actions/workflows/ci.yml)

Agent Rewind is a self-hosted debugger and experiment service for coding agents.
Open a failed run, inspect its decisions, restore a checkpoint, and change one
action or tool observation. Then test whether that intervention helps across
fresh continuations of the same run.

The main output is an **intervention study**: a frozen candidate, unchanged
control branches, independent confirmation trials, uncertainty bounds, and the
underlying trajectories. A successful branch is useful. It is not, by itself,
evidence that the intervention is reliable.

## What works

- **Real execution:** model-driven agents use shell, read, and write tools in
  disposable Linux sandboxes. No scripted policy runs in the application.
- **Restorable checkpoints:** serialized agent state, content-addressed file
  trees, modes, modified times, pinned image identity, and hash-linked events.
- **Two intervention types:** replace an action, or replace an observation while
  preserving the original tool's actual filesystem effects.
- **Automatic investigation:** rank suspicious decisions, ask the policy for
  alternatives, screen candidates with a negative control, then freeze one
  candidate for confirmation on fresh trial seeds.
- **Auditable evidence:** paired binary outcomes, conservative 95% effect
  intervals, exact discordance tests, and visible missing outcomes.
- **Team infrastructure:** PostgreSQL jobs with fenced leases, encrypted local
  or S3 artifacts, cancellation, OIDC login with PKCE, scoped API keys, and roles.
- **A browser workbench:** timeline, checkpoint files, branch editor, trajectory
  comparison, job status, study plots, and JSON report export.

This is an initial release for controlled Python coding workloads. The supported
execution boundary is explicit: only `/workspace` and serialized policy state
persist between tools. Process memory, background services, external databases,
and network side effects are not restored. See [architecture](docs/ARCHITECTURE.md)
and [security boundaries](docs/SECURITY.md) before deploying.

## Start locally

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and a Docker daemon.
The model endpoint must support chat-completions requests with JSON output.

```sh
git clone https://github.com/spei04/agent-rewind.git
cd agent-rewind
uv sync --frozen --group dev
cp .env.example .env
uv run rewind init
```

`init` fills empty encryption and bootstrap keys. Keep `.env` private; Git ignores
it. Configure these worker settings:

```dotenv
REWIND_MODEL_URL=https://api.openai.com/v1/chat/completions
REWIND_MODEL_API_KEY=your-provider-key
REWIND_MODEL_NAME=your-model-id
REWIND_MODEL_INPUT_PRICE=your-input-price-per-million-tokens
REWIND_MODEL_OUTPUT_PRICE=your-output-price-per-million-tokens
REWIND_ALLOWED_IMAGES=python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d
```

Use a pinned model version where available. Prices are deployment configuration,
not inferred from the model name. Model credentials remain on workers and never
enter a sandbox or the browser.

Reasoning models can set `REWIND_MODEL_REASONING_EFFORT=high` and a larger
`REWIND_MODEL_MAX_OUTPUT_TOKENS` (for example, 8192) to allow for reasoning and
the final action. The reasoning setting is part of the saved policy identity.
`REWIND_MODEL_MAX_INPUT_TOKENS` bounds input before dispatch using a conservative
byte-based estimate. Configure input prices to cover cache writes and every
pricing tier allowed by this bound. Usage-derived costs are estimates at those
configured rates, not provider invoices.

Pull the environment explicitly:

```sh
docker pull python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d
```

Linux production workers require gVisor. For **trusted local development only**, a
machine without gVisor can explicitly set:

```dotenv
REWIND_SANDBOX_RUNTIME=runc
REWIND_ALLOW_INSECURE_RUNTIME=true
```

Start the service and a worker in separate terminals:

```sh
uv run rewind serve
uv run rewind worker
```

Open [localhost:8080](http://127.0.0.1:8080). Sign in with the local
`REWIND_BOOTSTRAP_KEY`, then load `examples/invoice-task.json` under **Record a
run**. This submits a real model-backed coding task. Its outcome is not forced;
strong models may solve it immediately. Investigations require a failed run.

Use **Create branch** to edit one decision, or **Investigate failure** to propose
and evaluate interventions automatically. Jobs reserve budget before model
calls. The UI reports conservative reservations, not a provider billing total.

## Use from Python

```python
import json
import os
from pathlib import Path
from agent_rewind.models import TaskSpec
from agent_rewind.sdk import Client

task = TaskSpec.model_validate(json.loads(Path("examples/invoice-task.json").read_text()))
with Client("http://127.0.0.1:8080", os.environ["REWIND_API_TOKEN"]) as client:
    job_id = client.record(task)
    print(job_id)
```

The API schema is available at `/api/schema` after authentication. See
[the extension contract](docs/EXTENDING.md) for custom policies and runners.

## The research angle

[AgentReplay](https://github.com/gadda00/agentreplay) emphasizes intercepted
recordings, deterministic playback, and counterfactual mutation. Agent Rewind
focuses on **selecting and evaluating interventions through new executions**.

| Question | Agent Rewind's mechanism |
| --- | --- |
| Where should I intervene? | Rank errors, repetition, and workspace changes; generate alternative actions. |
| Did the edit itself help? | Compare treatment with an unchanged continuation from the same boundary. |
| Did discovery pick a lucky winner? | Freeze the candidate before a separate confirmation phase. |
| What happened to failed trials? | Retain partial runs, missing outcomes, and worst-case sensitivity bounds. |
| What does the conclusion apply to? | The specific task, checkpoint, policy, image, and evaluator. |

Heuristic location scores are hypotheses, not causal attribution. Provider seeds
are advisory, and many endpoints do not support them. The design randomizes
control/treatment order within pairs; it never claims bit-exact live model replay.
See [the experimental protocol](docs/RESEARCH.md).

## Deploy and verify

- [Deployment and operations](docs/DEPLOYMENT.md)
- [Architecture and state contracts](docs/ARCHITECTURE.md)
- [Security boundaries](docs/SECURITY.md)
- [Research protocol](docs/RESEARCH.md)
- [Extending the system](docs/EXTENDING.md)
- [Implementation plan](docs/PLAN.md)

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy agent_rewind
uv run pytest -q
```

The default tests use explicit test-only policies. To exercise actual sandbox
execution, set `REWIND_TEST_DOCKER=1`; set `REWIND_TEST_RUNTIME=runsc` to require
gVisor. Set `REWIND_TEST_POSTGRES` to a disposable PostgreSQL database to exercise
concurrent claims and budget reservations. CI runs both PostgreSQL and gVisor
integration checks without model credentials.

MIT licensed.
