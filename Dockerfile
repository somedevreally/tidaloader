# Stage 1: Frontend Builder
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install && \
    npm install @rollup/rollup-linux-x64-musl --save-optional
COPY frontend/ ./
RUN npm run build

# Stage 2: Python Dependency Builder
FROM python:3.11-slim AS python-builder
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 3: FFmpeg Static Binary Provider
FROM mwader/static-ffmpeg:7.1 AS ffmpeg

# Stage 4: Final Image
FROM python:3.11-slim
WORKDIR /app

# Install runtime system dependencies (minimal)
# libchromaprint-tools: for fpcalc (audio fingerprinting)
# curl: for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libchromaprint-tools \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
ARG USER_UID=1000
ARG USER_GID=1000
RUN groupadd -g ${USER_GID} appuser && \
    useradd -m -u ${USER_UID} -g appuser appuser

# Copy Python dependencies from builder
COPY --from=python-builder /root/.local /home/appuser/.local

# Copy FFmpeg static binaries
COPY --from=ffmpeg /ffmpeg /usr/local/bin/
COPY --from=ffmpeg /ffprobe /usr/local/bin/

# Copy Backend Code
COPY backend/ ./backend/

# Copy Frontend Build
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Setup Directories and Permissions
RUN mkdir -p /music && \
    chown -R appuser:appuser /app /music

# Env vars
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

WORKDIR /app/backend
USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8001/api/health || exit 1

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"]