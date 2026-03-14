#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_DIR="$(cd "${BACKEND_DIR}/.." && pwd)"

if [[ -x "${PROJECT_DIR}/venv/bin/python" ]]; then
  PYTHON_BIN="${PROJECT_DIR}/venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

if [[ -x "${PROJECT_DIR}/venv/bin/celery" ]]; then
  CELERY_BIN="${PROJECT_DIR}/venv/bin/celery"
else
  CELERY_BIN="${CELERY_BIN:-celery}"
fi

cd "${BACKEND_DIR}"

export APP_ENV="${APP_ENV:-dev}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"

QUEUE_LIST="${CELERY_QUEUES_OVERRIDE:-$("${PYTHON_BIN}" - <<'PY'
import contextlib
import io
import os
import sys

os.environ.setdefault("APP_ENV", os.environ.get("APP_ENV", "dev"))

stdout_buffer = io.StringIO()
with contextlib.redirect_stdout(stdout_buffer):
    from django.conf import settings

    queue_list = ",".join(settings.ALL_CELERY_QUEUE_NAMES)

sys.stdout.write(queue_list)
PY
)}"

echo "Starting Celery worker with broker ${REDIS_URL}"
echo "Listening on queues: ${QUEUE_LIST}"

exec "${CELERY_BIN}" -A moio_platform worker \
  -E \
  -l "${CELERY_LOG_LEVEL:-info}" \
  --pool="${CELERY_POOL:-threads}" \
  --concurrency="${CELERY_CONCURRENCY:-2}" \
  --max-memory-per-child="${CELERY_MAX_MEMORY_PER_CHILD:-128000}" \
  -Q "${QUEUE_LIST}" \
  "$@"
