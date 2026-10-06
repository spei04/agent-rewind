# Implementation plan

Agent Rewind is a self-hosted experiment service for Python coding agents. The
unit of debugging is an intervention study: a frozen checkpoint, a specific
change, matched control branches, and independent confirmation trials.

## Delivery sequence

1. Define versioned task, event, checkpoint, intervention, and study contracts.
2. Implement immutable, encrypted artifact storage and transactional metadata.
3. Execute real code in bounded containers; require the hardened runtime in
   production and restore each tool invocation from its workspace snapshot.
4. Integrate a model-driven Python coding agent through a stateful policy API.
5. Add durable jobs, cancellation, audit records, API keys, and identity login.
6. Rank intervention locations, screen candidates, and confirm a frozen winner
   with fresh trials. Retain failures and budget exhaustion in the result.
7. Build the run timeline, branch editor, comparisons, and study evidence UI.
8. Exercise storage, concurrency, authentication, isolation, replay, and
   experimental accounting. Publish deployment and extension documentation.

## Release boundary

The initial release supports one organization per deployment, sequential Python
agents, serialized policy state, ordinary shell commands, UTF-8 task manifests,
binary workspace snapshots, and isolated executable evaluators. It does not
restore arbitrary process memory or production databases. Network-dependent
tasks and uninstrumented external effects are outside the supported boundary.

The service owns its PostgreSQL database and artifact bucket. Neither is an
adopter's application database. A private network limits reachability; API
authentication and roles still apply.

## Validation gates

- Changes to the source run never occur during branching.
- Event chains and artifact hashes are verified on read.
- Missing runtime, image, restore state, or replay data causes a clear failure.
- Worker loss cannot publish a result under an expired lease.
- Model calls reserve budget before dispatch; ambiguous failures keep the charge.
- Confirmation uses new trial seeds and a candidate frozen before those trials.
- No synthetic-policy result is presented as evidence about real models.
- A release distinguishes implemented support from deployment tests actually run.
