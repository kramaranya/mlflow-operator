# MLflow Helm Chart

This chart deploys MLflow with Kubernetes authentication enabled. TLS is terminated directly in the MLflow pod using uvicorn options; certificates are loaded from `tls.secretName` (on OpenShift this is provided automatically by the service-ca operator).

- Authorization mode defaults to `self_subject_access_review` handled directly by MLflow.
- MLflow listens on port 8443 with TLS.
- Health probes and traffic use HTTPS end-to-end.
- This standalone chart does not orchestrate MLflow database migrations.

Set `mlflow.backendStoreUri` (or `mlflow.backendStoreUriFrom`) explicitly; it is required and should not rely on implicit defaults.

## Read-replica backend routing

With MLflow 3.14 or later, set one optional read-replica URI to route supported tracking and model-registry reads away from the primary database:

```yaml
mlflow:
  backendStoreUriFrom:
    secretKeyRef:
      name: mlflow-db-credentials
      key: backend-store-uri
  readReplicaBackendStoreUriFrom:
    secretKeyRef:
      name: mlflow-db-credentials
      key: read-replica-backend-store-uri
```

For a URI without credentials, `mlflow.readReplicaBackendStoreUri` can be used directly. When neither replica value is set, all operations continue to use the primary backend.

MLflow uses one replica URI for both tracking and model-registry reads. The replica must have a compatible schema, and its availability and data freshness depend on the database topology. This standalone chart does not migrate either database or provide application-level failover to the primary.

## Dedicated artifact server

Set `artifactsServer.enabled=true` to render a separate MLflow Deployment and Service running
with `--serve-artifacts`, the same metadata stores as tracking, and server-side job execution
disabled. Also set `mlflow.serveArtifacts=false`, configure
`artifactsServer.artifactsDestination`, and set `artifactsServer.artifactRoot` to the externally
reachable artifact API URL that both metadata-connected servers should use as their default root.
For example:

```yaml
mlflow:
  serveArtifacts: false
artifactsServer:
  enabled: true
  artifactsDestination: s3://mlflow-artifacts
  artifactRoot: https://mlflow.example.com/mlflow-artifacts/api/2.0/mlflow-artifacts/artifacts
  allowedHosts:
    - mlflow.example.com
```

`artifactsServer.allowedHosts` defaults to `["*"]` so Gateway Host headers reach the dedicated
server, matching operator-managed deployments. Standalone production installs should replace the
wildcard with their externally reachable Gateway hostname or hostnames.

Dedicated artifact serving requires remote SQL metadata stores; inline SQLite metadata URIs are
rejected. Secret-backed metadata URIs cannot be inspected by standalone Helm and must resolve to
remote SQL; the operator resolves and validates configured Secret keys before rendering. The
tracking Deployment does not mount the PVC in this mode. When
`artifactsServer.artifactsDestination` uses `file://`, set `storage.enabled=true`; one artifact
replica may use `ReadWriteOnce`, while multiple replicas require `ReadWriteMany`. Remote artifact
destinations such as S3 do not mount persistent storage.
`temporaryStorage.sizeLimit` configures the writable `/tmp` `emptyDir` in both server pods and
defaults to `1Gi`; increase it for larger or more concurrent proxied artifact transfers.
When garbage collection is enabled, the CronJob resolves `mlflow-artifacts:/` locations through
the internal artifact Service and its static prefix. Without a dedicated server, it uses the
tracking Service and tracking static prefix instead.
Dynamic Resource Allocation claims are workload-specific: configure artifact pod claims through
`artifactsServer.resourceClaims` and reference them from `artifactsServer.resources.claims`.
Artifact pods never inherit top-level tracking claims; only requests and limits are inherited when
`artifactsServer.resources` is empty.

The standalone chart creates only the artifacts Deployment and Service. It does not create an
Ingress or `HTTPRoute`; expose the Service at the configured `artifactRoot` yourself. To preserve
existing `mlflow-artifacts:/` locations, route and rewrite the complete tracking-relative
`/api/2.0/mlflow-artifacts` and `/ajax-api/2.0/mlflow-artifacts` proxy families to the artifact
Service's `artifactsServer.staticPrefix`, including artifact, multipart, and presigned operations.
To preserve UI artifact operations, route and rewrite these tracking-relative paths as well:
`/get-artifact`, `/model-versions/get-artifact`,
`/ajax-api/2.0/mlflow/artifacts/list`, `/ajax-api/2.0/mlflow/upload-artifact`,
`/ajax-api/2.0/mlflow/get-artifact`, both v2 and v3 `get-trace-artifact` paths, and
`/ajax-api/2.0/mlflow/logged-models/`. The logged-model prefix is necessarily broader than its
artifact handlers because portable Gateway API matching cannot wildcard the model ID in the middle;
non-artifact logged-model requests under that prefix will also reach the artifact Deployment.
Both servers
use the same image, Kubernetes workspace provider, artifact credentials, scheduling settings, and
security contexts. The artifact container receives the same primary, registry, and optional
read-replica store URI configuration as tracking. Provide
the TLS Secret configured by `artifactsServer.tls.secretName` when
it is not provisioned by an OpenShift service-ca annotation.
When metrics are enabled, the `ServiceMonitor` selects only the tracking Service; the artifact
server does not run with `--expose-prometheus`.
Configured CA bundles provide the artifact container with the same PostgreSQL and MySQL TLS
environment as the tracking container. Because the standalone chart does not orchestrate
migrations, stop both metadata-connected Deployments before migrating their shared stores.

See `values.yaml` for the full list of configurable settings.
