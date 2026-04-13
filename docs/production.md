# Production Considerations

This document addresses operational questions raised in the assessment brief.
Each section describes the current state and what a production deployment would require.

---

## 1. Sensitive configuration in Kubernetes

**Current state:** All secrets are read from environment variables via `pydantic-settings`.
No secrets are baked into the image or committed to the repository.

**Kubernetes approach:**

Sensitive values (`AZURE_OPENAI_API_KEY` or `OPENAI_API_KEY`) are stored in a
`Secret` object and injected as environment variables via `secretKeyRef`.
Non-sensitive values (`AZURE_OPENAI_ENDPOINT`, `OPENAI_MODEL`, etc.) live as
plain `env` entries in the Deployment spec.

See `k8s/secret.yaml.example` for the template.

For production workloads, the `Secret` manifest itself should not be committed.
Use one of:

- **Sealed Secrets** — encrypt the Secret with a cluster-scoped key; commit the
  encrypted resource; the in-cluster controller decrypts at apply time.
- **External Secrets Operator** — sync secrets from Vault, AWS SSM, GCP Secret
  Manager, or Azure Key Vault into Kubernetes Secrets automatically.
- **`kubectl create secret` in CI/CD** — generate the Secret from a secrets manager
  in the pipeline without storing it in source control.

---

## 2. Endpoints for orchestration

The service exposes two dedicated health endpoints:

| Endpoint | Purpose | Expected consumer |
| --- | --- | --- |
| `GET /api/v1/healthz` | **Liveness** — process is alive and responding | Kubernetes `livenessProbe`, Docker `HEALTHCHECK` |
| `GET /api/v1/readyz` | **Readiness** — DB is reachable, service can handle traffic | Kubernetes `readinessProbe`, load-balancer health checks |

`/healthz` always returns `200 {"status": "ok"}` as long as the Python process is
running. It is intentionally cheap — no I/O.

`/readyz` executes `SELECT 1` against SQLite. Returns `200` on success, `503` on
failure. Kubernetes will stop routing traffic to a pod when readiness fails,
which prevents requests from hitting a pod whose database mount is not yet ready.

Both probes are wired into `k8s/deployment.yaml`.

---

## 3. Visibility into service health and performance

**Logging (implemented)**

All request lifecycle events are logged as structured JSON with stable keys:
`request_id`, `method`, `path`, `status_code`, `duration_ms`. LLM tool calls,
provider errors, and SSE connections are also logged with contextual fields.
Log output goes to stdout, where a collector (Fluentd, Filebeat, Datadog Agent)
can pick it up.

**Metrics (TODO)**

The current implementation does not expose a metrics endpoint.
For production, add [prometheus-fastapi-instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator):

```python
# app/config/setup.py
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
```

This provides `http_requests_total`, `http_request_duration_seconds`, and custom
LLM latency histograms. Scrape with Prometheus; visualise in Grafana.

**Tracing (TODO)**

Distributed tracing with OpenTelemetry would allow correlating LLM latency,
DB queries, and HTTP calls into a single trace. Add
`opentelemetry-instrumentation-fastapi` and export to Jaeger or OTLP.

---

## 4. Persistent data in containerised deployments

**Problem:** SQLite is stored inside the container by default
(`/qna_rag/app/data/qna_rag.sqlite3`). The file is lost when the container is
removed.

**Solution for Docker:**

Mount a host directory or named volume:

```bash
docker run --rm \
  --env-file app/envs/.env \
  -v qna_rag_data:/qna_rag/app/data \
  -p 8000:8000 \
  qna-rag
```

Override the path via `DATABASE_PATH=/qna_rag/app/data/qna_rag.sqlite3`
(already the default) so the app writes into the mounted volume.

**Solution for Kubernetes:**

A `PersistentVolumeClaim` with `ReadWriteOnce` access mode provides durable
storage that survives pod restarts. See `k8s/pvc.yaml` and the `volumeMounts`
section of `k8s/deployment.yaml`.

**SQLite scaling limit:** `ReadWriteOnce` restricts the Deployment to a single
replica, because only one node can mount the volume for writing at a time. This
is acceptable for low-to-medium load. For higher throughput, migrate to
PostgreSQL (with asyncpg) and switch to `ReadWriteMany` storage, or use a
managed database service.

---

## 5. TLS termination and port configuration

**Current state:** The service listens on plain HTTP on port 8000. TLS is not
handled by the application.

**Recommended approach — terminate TLS at the ingress layer:**

```
Internet → (HTTPS 443) → Ingress / Load Balancer → (HTTP 8000) → qna-rag pod
```

On Kubernetes, use an Ingress controller (nginx, Traefik) with cert-manager to
provision Let's Encrypt certificates automatically:

```yaml
# Example Ingress snippet
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: qna-rag
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
    - hosts: [qna-rag.example.com]
      secretName: qna-rag-tls
  rules:
    - host: qna-rag.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: qna-rag
                port:
                  number: 80
```

The application port (8000) is configurable via `APP_PORT`. The Deployment
exposes `containerPort: 8000`; the Service maps it to port 80 internally.
External port binding is handled by the Ingress, not the application.

**Can this service be deployed correctly without an Ingress?** Yes.
Ingress is not required for a correct Kubernetes deployment of this service.
The current manifests already work without it for these cases:

- internal cluster-to-cluster traffic through the `ClusterIP` Service
- local operator access via `kubectl port-forward`
- external exposure through a `LoadBalancer` or `NodePort` Service instead of Ingress

What Ingress adds is not correctness of the workload itself, but HTTP routing
features: host/path routing, centralized TLS termination, and a stable public
entrypoint. If none of that is needed, omitting Ingress is perfectly valid.

---

## Bonus: Potential performance improvements

| Area | Current | Improvement |
| --- | --- | --- |
| **Knowledge retrieval** | Reads all files from disk on every search query | Build an in-memory TF-IDF or BM25 index at startup via `KnowledgeIndexer`; rebuild on SIGHUP or a `POST /admin/reload-knowledge` endpoint |
| **LLM calls** | Synchronous SDK call offloaded to a thread pool via `asyncio.to_thread` | Switch to the async OpenAI client (`AsyncOpenAI` / `AsyncAzureOpenAI`) to avoid thread pool overhead under concurrent load |
| **SQLite concurrency** | Default journal mode | Enable WAL mode (`PRAGMA journal_mode=WAL`) at connection time to allow concurrent readers alongside one writer; reduces lock contention for SSE polling |
| **SSE polling** | Fixed 0.5 s polling interval per open stream | Reduce interval or replace with SQLite update hooks / `asyncio.Event` notifications within a single process to cut delivery latency |
| **Response caching** | No caching | Cache identical questions with short TTL using a lightweight in-memory LRU cache (`functools.lru_cache` on the retrieval result) |
