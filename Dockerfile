# Build a wheel once so the runtime image contains no compiler or source checkout.
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml README.md ./
COPY backend/app backend/app
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

# Run the API as an unprivileged user with a container-native health probe.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8000
RUN addgroup --system paylens && adduser --system --ingroup paylens paylens
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY alembic.ini /app/alembic.ini
COPY backend/migrations /app/backend/migrations
WORKDIR /app
USER paylens
EXPOSE 8000
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--no-access-log"]
