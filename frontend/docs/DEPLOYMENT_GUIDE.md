# Deployment Guide

This guide covers Kubernetes deployment for the Moio frontend using the bundled Helm chart and GitHub Actions workflow.

## Prerequisites

* A Kubernetes cluster (v1.26+) with:
  * An ingress controller (e.g., nginx-ingress or Traefik).
  * [cert-manager](https://cert-manager.io/) configured with the `letsencrypt-http` ClusterIssuer to mint TLS certificates for `ui.moio.ai` using the `ui-moio-ai-tls` secret.
* `kubectl` and `helm` CLIs installed locally for manual operations.
* Access to [GitHub Container Registry](https://ghcr.io) and the repository with permissions to push packages and manage Actions secrets.

## Helm chart overview

* Location: `deploy/chart`
* Renders the following resources:
  * `Deployment` (with configurable replicas, resource requests/limits, probes, and security context)
  * `Service`
  * `Ingress`
  * `HorizontalPodAutoscaler`
  * `ConfigMap`
  * `Secret`
  * `ServiceAccount`
* Container settings:
  * Exposes container port `5000`.
  * Health probes target `/healthz` (liveness/startup) and `/readyz` (readiness).
  * Environment variables `NODE_ENV`, `PORT`, and any provided secrets/config maps are injected automatically.

## Initial cluster setup

Replace placeholders with your organization-specific values.

```bash
# Namespace for the application
kubectl create namespace moio-frontend

# Image pull secret (if not using the default GitHub Actions authentication)
kubectl create secret docker-registry registry-4 \
  --namespace moio-frontend \
  --docker-server=ghcr.io \
  --docker-username="<ghcr-username>" \
  --docker-password="<ghcr-token>"

# (Optional) Pre-create the TLS secret if not managed automatically by cert-manager
kubectl create secret tls ui-moio-ai-tls \
  --namespace moio-frontend \
  --cert=path/to/fullchain.pem \
  --key=path/to/privkey.pem

# Optional: secret for runtime credentials expected by the app
kubectl create secret generic moio-frontend-app-secret \
  --namespace moio-frontend \
  --from-literal=SESSION_SECRET="change-me"
```

## GitHub Actions deployment pipeline

The workflow in `.github/workflows/deploy.yml` performs the following when triggered by a push to `main` or a manual dispatch:

1. Installs dependencies and runs `npm run build` to validate the project.
2. Authenticates to GHCR and builds/pushes the Docker image tagged with the commit SHA and `latest`.
3. Bootstraps `kubectl` and `helm` using the kubeconfig stored in repository secrets.
4. Validates rendered manifests with `helm template` and a `kubectl apply --dry-run`.
5. Executes `helm upgrade --install` and waits for the deployment rollout to complete.

### Required repository secrets

| Secret | Description |
| ------ | ----------- |
| `KUBE_CONFIG` | Base64-encoded kubeconfig granting access to the target cluster. |
| `KUBE_NAMESPACE` | Namespace to deploy the chart into (e.g., `moio-frontend`). |
| `HELM_RELEASE` | Name of the Helm release (e.g., `moio-frontend`). |
| `GHCR_TOKEN` | Personal access token or fine-grained PAT with `packages:write` scope for GHCR (optional if `GITHUB_TOKEN` is sufficient). |
| `GHCR_USERNAME` | GHCR username tied to the token (optional; only needed if using a PAT). |
| `HELM_EXTRA_FLAGS` | Optional additional flags appended to the `helm upgrade` command (e.g., `--values deploy/chart/values-staging.yaml`). |

### Optional secrets

| Secret | Description |
| ------ | ----------- |
| `APP_RUNTIME_SECRETS` | JSON or multi-line content that can be converted into Kubernetes secrets via custom steps. (Not consumed by default workflow.) |

## Overriding chart values

Create environment-specific values files (e.g., `deploy/chart/values-staging.yaml`) to override defaults such as replica counts, ingress hosts, TLS certificates, and environment variables. Example snippet:

```yaml
image:
  repository: ghcr.io/marttottdc/moio-frontend
  tag: "1.0.0"

service:
  type: ClusterIP

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: ui.moio.ai
      paths:
        - path: /
          pathType: Prefix
  tls:
    - hosts:
        - ui.moio.ai
      secretName: ui-moio-ai-tls

env:
  config:
    NODE_ENV: production
  secrets:
    SESSION_SECRET: "${SESSION_SECRET}"
```

Deploy with custom values using either the GitHub Actions secret `HELM_EXTRA_FLAGS` or manually:

```bash
helm upgrade --install moio-frontend deploy/chart \
  --namespace moio-frontend \
  --set image.repository=ghcr.io/marttottdc/moio-frontend \
  --set image.tag=$(git rev-parse HEAD) \
  --values deploy/chart/values-staging.yaml
```

## Health checks

The container exposes `/health`, `/healthz`, and `/readyz` for liveness and readiness probes. Kubernetes probes defined in the chart align with these endpoints, enabling safe rolling deployments and automated restarts.
