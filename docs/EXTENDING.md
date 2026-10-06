# Extension contracts

## Python policy

The `Policy` protocol in `agent_rewind/policy.py` separates decision making from
sandbox execution:

```python
class Policy:
    def identity(self): ...
    def initial(self, task): ...
    def propose(self, state, step, seed): ...
    def observe(self, state, action, result): ...
```

State must be complete, JSON-serializable, and sufficient to continue. Avoid
hidden module globals, private caches, or unrecorded conversation state.
`propose` returns an `Action` and an auditable decision record. `observe` returns
the next state. `identity` must change when the policy code, prompt, model
configuration, or relevant dependencies change.

The bundled `ChatPolicy` is used by the default worker. To integrate an existing
Python agent, implement this protocol and construct `Engine` with your policy
from a trusted worker entrypoint. Do not accept import paths or arbitrary policy
code from API requests. The public Python `Client` submits tasks to managed
workers; it does not inject code into a worker process.

Automatic candidate proposal currently expects chat-style state with a
`messages` list. A different policy can submit explicit `StudyRequest`
interventions or add its own proposal generator while reusing the same study
protocol and engine.

## Runner

`Runner` owns image resolution, tool execution, and isolated evaluation. An
implementation must enforce image authorization, resource limits, path safety,
cancellation, and the checkpoint contract. It returns actual filesystem state and
tool observations; it cannot fabricate a successful grader outcome.

A managed sandbox provider can implement the same interface. Before adopting
one, establish its snapshot semantics, supported file types, network controls,
credential boundaries, cancellation behavior, and artifact export guarantees.
The current Docker runner is the concrete implementation, not a placeholder.

## Evaluator

Task authors provide evaluator source and a command such as
`python -I /evaluator/grade.py`. Evaluator files mount read-only at `/evaluator`
and never enter agent workspaces. The command runs in a new sandbox with the
final candidate workspace. Zero exit means success; nonzero exit means failure.

Write graders that are robust to the candidate's threat model. Avoid trusting a
candidate's own tests or printed claims. Read-only evaluator source alone cannot
prevent all forms of test evasion by imported code.

## Experiments

Manual studies accept between one and eight interventions. Study configuration
is frozen and hashed before screening. The winning intervention is committed
before confirmation. New proposal strategies should preserve this separation
and retain all missing outcomes. Do not pool exploratory screening samples into
the confirmation estimate.
