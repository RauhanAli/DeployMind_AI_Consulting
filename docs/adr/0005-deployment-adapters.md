# ADR 0005: Deployment adapters with honest status

* Status: accepted
* Date: 2026-10-30

## Context
The platform must show a genuine build → test → release → health-check → rollback workflow locally, and map
cleanly to cloud deployment, without pretending a cloud deployment happened.

## Decision
* A `DeploymentAdapter` protocol (`build`, `test`, `release`, `health`, `stop`) with three implementations:
  **local Docker** (fully real), **GitHub Actions** (workflow_dispatch + polling) and **AWS ECS**
  (task-definition revision + service update + stability waiter).
* Unconfigured adapters raise `AdapterNotConfigured`, and the deployment fails with that reason.
* Releases are blue/green: the new container must pass health checks before the old one stops. Rollback
  re-releases the previous image without rebuilding.
* Production requires approval by a different person. Each release gets its own runtime token.

## Consequences
* The local demo performs real deployments. Cloud adapters are real code paths that need credentials.
* The local adapter needs the Docker socket and is not for production use.
