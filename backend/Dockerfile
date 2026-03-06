# =====================================================
# Base image with system dependencies (cached)
# =====================================================
FROM python:3.12.8 AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    pkg-config \
    tesseract-ocr \
    tesseract-ocr-spa \
    tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*


# =====================================================
# Builder — Python dependencies only
# =====================================================
FROM base AS builder

COPY requirements.txt .

RUN pip install --upgrade pip==24.3.1 \
 && pip install -r requirements.txt


# =====================================================
# Runtime image
# =====================================================
FROM base

ARG IMAGE_TAG=latest
ENV IMAGE_TAG=${IMAGE_TAG}

LABEL org.opencontainers.image.version=${IMAGE_TAG}

COPY --from=builder /usr/local /usr/local

COPY . /app/

EXPOSE 8010

CMD ["hypercorn", "-c", "hypercorn_config.py", "moio_platform.asgi:application"]
