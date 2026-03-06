# Containerizing the Moio Frontend

This project ships with a multi-stage Dockerfile that builds the Moio frontend bundle and Node.js API, then copies the compiled output into a slim runtime image. The container listens on port `5000` and exposes lightweight health probes.

## Build the image

```bash
docker build -t moio-frontend:latest .
```

To push the image to the default registry target (`ghcr.io/marttottdc/moio-frontend`), tag it explicitly and push:

```bash
docker tag moio-frontend:latest ghcr.io/marttottdc/moio-frontend:latest
docker push ghcr.io/marttottdc/moio-frontend:latest
```

The build performs the following stages:

1. Install dependencies with `npm ci` (builder stage).
2. Compile the Vite client and server bundle via `npm run build`.
3. Copy the compiled `dist` output and production dependencies into a Node.js 20 slim runtime configured to run as a non-root user.

## Run the container locally

```bash
docker run --rm -p 5000:5000 \
  -e NODE_ENV=production \
  -e PORT=5000 \
  moio-frontend:latest
```

Health endpoints are exposed on `/health`, `/healthz`, and `/readyz`. You can verify the container from another terminal:

```bash
curl http://localhost:5000/healthz
```

To provide additional configuration or secrets, supply environment variables or mount files into `/app/config` (consumed via the Helm chart ConfigMap options).
