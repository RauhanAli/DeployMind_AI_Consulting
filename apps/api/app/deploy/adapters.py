"""Deployment adapter abstraction.

- LocalDockerAdapter: genuinely builds the assistant-service image, runs its unit tests inside the image,
  starts the new container (blue/green), health-checks it and only then stops the previous container.
- GitHubActionsAdapter: dispatches the deploy workflow through the GitHub REST API and polls the run.
- AwsEcsAdapter: registers a new task-definition revision and updates an ECS/Fargate service via boto3.
  Requires an image already pushed to ECR (normally by GitHub Actions) and AWS credentials.

Adapters never report success for work they did not do: unconfigured adapters raise AdapterNotConfigured.
"""

import socket
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import settings

LogFn = Callable[[str, str, str], None]  # (stage, message, level)


class AdapterError(Exception):
    pass


class AdapterNotConfigured(AdapterError):
    pass


@dataclass
class DeployContext:
    deployment_id: str
    environment_id: str
    environment: str
    app_id: str
    version: str
    image_tag: str | None  # set for rollbacks / pre-built images
    env_vars: dict[str, str]
    resources: dict
    previous_runtime: dict = field(default_factory=dict)


class DeploymentAdapter(Protocol):
    name: str
    honest_label: str

    def build(self, ctx: DeployContext, log: LogFn) -> str: ...
    def test(self, ctx: DeployContext, image_tag: str, log: LogFn) -> None: ...
    def release(self, ctx: DeployContext, image_tag: str, log: LogFn) -> dict: ...
    def health(self, runtime: dict) -> tuple[bool, dict]: ...
    def stop(self, runtime: dict, log: LogFn | None = None) -> None: ...


def http_health(url: str) -> tuple[bool, dict]:
    try:
        r = httpx.get(f"{url}/health", timeout=3)
        body = r.json()
        return r.status_code == 200 and body.get("status") == "ok", body
    except Exception as exc:
        return False, {"error": str(exc)[:200]}


# ------------------------------------------------------------------ local docker
class LocalDockerAdapter:
    name = "local_docker"
    honest_label = "Local Docker (real containers on this machine)"

    def __init__(self) -> None:
        # The Docker connection is opened lazily: health checks are plain HTTP and must work from processes
        # without Docker socket access (e.g. the API container in docker-compose).
        self._client = None
        self.src = Path(settings.assistant_service_path)

    @property
    def client(self):
        if self._client is None:
            import docker

            try:
                client = docker.from_env(timeout=120)
                client.ping()
            except Exception as exc:
                raise AdapterNotConfigured(f"Docker daemon is not reachable: {exc}") from exc
            if not (self.src / "Dockerfile").exists():
                raise AdapterNotConfigured(f"Assistant service source not found at {self.src}")
            self._client = client
        return self._client

    def check(self) -> None:
        _ = self.client

    def _tag(self, ctx: DeployContext) -> str:
        return f"deploymind/assistant-{ctx.app_id[:8]}:{ctx.version}"

    def build(self, ctx: DeployContext, log: LogFn) -> str:
        tag = self._tag(ctx)
        log("build", f"docker build {self.src.name} -t {tag}", "info")
        try:
            for chunk in self.client.api.build(path=str(self.src), tag=tag, rm=True, decode=True,
                                               labels={"deploymind.app": ctx.app_id, "deploymind.version": ctx.version}):
                if "stream" in chunk and chunk["stream"].strip():
                    log("build", chunk["stream"].strip()[:500], "info")
                if "error" in chunk:
                    raise AdapterError(chunk["error"])
        except AdapterError:
            raise
        except Exception as exc:
            raise AdapterError(f"Image build failed: {exc}") from exc
        log("build", f"Built image {tag}", "info")
        return tag

    def test(self, ctx: DeployContext, image_tag: str, log: LogFn) -> None:
        log("test", "Running unit tests inside the image: python -m unittest -v", "info")
        try:
            out = self.client.containers.run(image_tag, ["python", "-m", "unittest", "-v"], remove=True,
                                             stdout=True, stderr=True)
            for line in out.decode(errors="replace").splitlines()[-40:]:
                log("test", line, "info")
        except Exception as exc:
            detail = getattr(exc, "stderr", b"") or b""
            for line in (detail.decode(errors="replace") if isinstance(detail, bytes) else str(detail)).splitlines()[-40:]:
                log("test", line, "error")
            raise AdapterError(f"Unit tests failed: {exc}") from exc

    def _free_port(self) -> int:
        lo, hi = settings.deploy_port_range
        used = set()
        for c in self.client.containers.list(filters={"label": "deploymind.managed=true"}):
            for binds in (c.attrs.get("HostConfig", {}).get("PortBindings") or {}).values():
                used.update(int(b["HostPort"]) for b in binds or [])
        for port in range(lo, hi + 1):
            if port in used:
                continue
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", port)) != 0:
                    return port
        raise AdapterError(f"No free port in range {lo}-{hi}")

    def release(self, ctx: DeployContext, image_tag: str, log: LogFn) -> dict:
        port = self._free_port()
        name = f"dm-{ctx.environment}-{ctx.app_id[:8]}-{ctx.deployment_id[:8]}"
        mem = int(ctx.resources.get("memory_mb", 512))
        cpu = float(ctx.resources.get("cpu", 0.5))
        log("release", f"Starting container {name} on port {port} (cpu={cpu}, memory={mem}MB)", "info")
        try:
            c = self.client.containers.run(
                image_tag, detach=True, name=name, environment=ctx.env_vars, ports={"8080/tcp": port},
                labels={"deploymind.managed": "true", "deploymind.environment_id": ctx.environment_id,
                        "deploymind.deployment_id": ctx.deployment_id},
                mem_limit=f"{mem}m", nano_cpus=int(cpu * 1e9), restart_policy={"Name": "unless-stopped"},
                extra_hosts={"host.docker.internal": "host-gateway"},
            )
        except Exception as exc:
            raise AdapterError(f"Container start failed: {exc}") from exc
        runtime = {"container_id": c.id, "container_name": name, "port": port, "image_tag": image_tag,
                   "url": f"http://{settings.local_deploy_public_host}:{port}",
                   "probe_url": f"http://{settings.local_deploy_probe_host}:{port}"}
        ok, details = False, {}
        for attempt in range(20):
            time.sleep(1.5)
            ok, details = self.health(runtime)
            if ok:
                break
            log("health_check", f"Attempt {attempt + 1}: not ready ({details.get('error') or details.get('status')})", "info")
        if not ok:
            logs = c.logs(tail=30).decode(errors="replace")
            for line in logs.splitlines():
                log("health_check", line, "error")
            self.stop(runtime)
            raise AdapterError(f"New container failed health checks: {details}")
        log("health_check", f"Healthy: {details}", "info")
        if ctx.previous_runtime.get("container_id"):
            log("release", f"Stopping previous container {ctx.previous_runtime.get('container_name')}", "info")
            self.stop(ctx.previous_runtime, log)
        runtime["health"] = details
        return runtime

    def health(self, runtime: dict) -> tuple[bool, dict]:
        return http_health(runtime.get("probe_url") or runtime["url"])

    def stop(self, runtime: dict, log: LogFn | None = None) -> None:
        import docker

        try:
            c = self.client.containers.get(runtime["container_id"])
            c.stop(timeout=5)
            c.remove()
        except docker.errors.NotFound:
            if log:
                log("release", "Previous container already removed", "info")


# ------------------------------------------------------------------ GitHub Actions
class GitHubActionsAdapter:
    name = "github_actions"
    honest_label = "GitHub Actions workflow_dispatch (requires GITHUB_TOKEN and GITHUB_REPOSITORY)"

    def __init__(self) -> None:
        if not (settings.github_token and settings.github_repository):
            raise AdapterNotConfigured("GITHUB_TOKEN and GITHUB_REPOSITORY must be configured")
        self.http = httpx.Client(base_url="https://api.github.com", timeout=20, headers={
            "Authorization": f"Bearer {settings.github_token}", "Accept": "application/vnd.github+json"})

    def build(self, ctx: DeployContext, log: LogFn) -> str:
        repo, wf = settings.github_repository, settings.github_deploy_workflow
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        r = self.http.post(f"/repos/{repo}/actions/workflows/{wf}/dispatches",
                           json={"ref": "main", "inputs": {"environment": ctx.environment, "version": ctx.version}})
        if r.status_code != 204:
            raise AdapterError(f"workflow_dispatch failed: {r.status_code} {r.text[:300]}")
        log("build", f"Dispatched {wf} on {repo} for {ctx.environment}", "info")
        for _ in range(120):
            time.sleep(10)
            runs = self.http.get(f"/repos/{repo}/actions/workflows/{wf}/runs",
                                 params={"created": f">={since}", "per_page": 1}).json().get("workflow_runs", [])
            if not runs:
                continue
            run = runs[0]
            log("build", f"Run {run['id']} status={run['status']} conclusion={run.get('conclusion')}", "info")
            if run["status"] == "completed":
                if run.get("conclusion") != "success":
                    raise AdapterError(f"Workflow run failed: {run['html_url']}")
                return f"{settings.aws_ecr_repository or repo}:{ctx.version}"
        raise AdapterError("Timed out waiting for workflow run")

    def test(self, ctx, image_tag, log) -> None:
        log("test", "Tests executed by the GitHub Actions workflow", "info")

    def release(self, ctx, image_tag, log) -> dict:
        log("release", "Release performed by the workflow's deploy job", "info")
        return {"image_tag": image_tag, "url": ctx.env_vars.get("PUBLIC_URL")}

    def health(self, runtime: dict) -> tuple[bool, dict]:
        if not runtime.get("url"):
            return False, {"error": "No public URL configured for this environment"}
        return http_health(runtime["url"])

    def stop(self, runtime, log=None) -> None:
        return None


# ------------------------------------------------------------------ AWS ECS / Fargate
class AwsEcsAdapter:
    name = "aws_ecs"
    honest_label = "AWS ECS Fargate (requires AWS credentials, cluster and ECR image)"

    def __init__(self) -> None:
        if not (settings.aws_ecs_cluster and settings.aws_ecr_repository):
            raise AdapterNotConfigured("AWS_ECS_CLUSTER and AWS_ECR_REPOSITORY must be configured")
        import boto3

        self.ecs = boto3.client("ecs", region_name=settings.s3_region)

    def _service(self, ctx: DeployContext) -> str:
        return f"{settings.aws_ecs_service_prefix}-{ctx.environment}-{ctx.app_id[:8]}"

    def build(self, ctx, log) -> str:
        tag = ctx.image_tag or f"{settings.aws_ecr_repository}:{ctx.version}"
        log("build", f"Using pre-built ECR image {tag} (built and pushed by CI)", "info")
        return tag

    def test(self, ctx, image_tag, log) -> None:
        log("test", "Image tests run in CI before push to ECR", "info")

    def release(self, ctx, image_tag, log) -> dict:
        svc = self._service(ctx)
        current = self.ecs.describe_services(cluster=settings.aws_ecs_cluster, services=[svc])["services"]
        if not current:
            raise AdapterError(f"ECS service {svc} does not exist; create it with infrastructure/terraform")
        td = self.ecs.describe_task_definition(taskDefinition=current[0]["taskDefinition"])["taskDefinition"]
        container = dict(td["containerDefinitions"][0])
        container["image"] = image_tag
        container["environment"] = [{"name": k, "value": v} for k, v in ctx.env_vars.items()]
        keep = ("family", "taskRoleArn", "executionRoleArn", "networkMode", "requiresCompatibilities", "cpu", "memory")
        new_td = self.ecs.register_task_definition(**{k: td[k] for k in keep if k in td},
                                                   containerDefinitions=[container])["taskDefinition"]
        log("release", f"Registered {new_td['taskDefinitionArn']}", "info")
        self.ecs.update_service(cluster=settings.aws_ecs_cluster, service=svc,
                                taskDefinition=new_td["taskDefinitionArn"],
                                desiredCount=int(ctx.resources.get("replicas", 1)))
        log("release", "Waiting for service to become stable", "info")
        self.ecs.get_waiter("services_stable").wait(cluster=settings.aws_ecs_cluster, services=[svc])
        return {"service": svc, "task_definition": new_td["taskDefinitionArn"], "image_tag": image_tag,
                "url": ctx.env_vars.get("PUBLIC_URL")}

    def health(self, runtime: dict) -> tuple[bool, dict]:
        s = self.ecs.describe_services(cluster=settings.aws_ecs_cluster, services=[runtime["service"]])["services"][0]
        ok = s["runningCount"] >= s["desiredCount"] > 0
        return ok, {"running": s["runningCount"], "desired": s["desiredCount"], "status": s["status"]}

    def stop(self, runtime, log=None) -> None:
        return None


ADAPTERS = {"local_docker": LocalDockerAdapter, "github_actions": GitHubActionsAdapter, "aws_ecs": AwsEcsAdapter}
_overrides: dict[str, Callable[[], DeploymentAdapter]] = {}


def register_adapter_override(name: str, factory: Callable[[], DeploymentAdapter]) -> None:
    """Used by tests to substitute a fake adapter."""
    _overrides[name] = factory


def get_adapter(name: str) -> DeploymentAdapter:
    if name in _overrides:
        return _overrides[name]()
    cls = ADAPTERS.get(name)
    if cls is None:
        raise AdapterNotConfigured(f"Unknown deployment adapter '{name}'")
    return cls()


WORKER_STATUS_KEY = "deploymind:adapter_status"


def worker_reported_status() -> list[dict] | None:
    """Deployments run on the worker, so its view of adapter availability is authoritative when present."""
    import json

    import redis

    try:
        raw = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=0.5, socket_timeout=0.5).get(WORKER_STATUS_KEY)
    except redis.RedisError:
        return None
    return json.loads(raw) if raw else None


def publish_worker_status() -> list[dict]:
    import json

    import redis

    status = [{**s, "checked_by": "worker"} for s in adapter_status()]
    redis.Redis.from_url(settings.redis_url).set(WORKER_STATUS_KEY, json.dumps(status), ex=300)
    return status


def effective_adapter_status() -> list[dict]:
    return worker_reported_status() or [{**s, "checked_by": "api"} for s in adapter_status()]


def adapter_status() -> list[dict]:
    out = []
    for name, cls in ADAPTERS.items():
        try:
            adapter = cls()
            if hasattr(adapter, "check"):
                adapter.check()
            out.append({"adapter": name, "available": True, "label": cls.honest_label})
        except AdapterNotConfigured as exc:
            out.append({"adapter": name, "available": False, "label": cls.honest_label, "reason": str(exc)})
    return out
