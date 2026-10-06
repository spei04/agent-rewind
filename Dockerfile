FROM python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d
RUN pip install --no-cache-dir uv==0.11.21
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY agent_rewind ./agent_rewind
RUN uv sync --frozen --no-dev --no-cache
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1
RUN useradd --uid 10001 --create-home rewind && mkdir -p /data && chown rewind /data
USER rewind
ENV REWIND_DATA_DIR=/data
EXPOSE 8080
CMD ["rewind", "serve", "--host", "0.0.0.0"]
