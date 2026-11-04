# Build context: NutriAthenaAgent directory.
FROM python:3.11-alpine3.22 AS builder

RUN sed -i 's@dl-cdn.alpinelinux.org@mirrors.aliyun.com@g' /etc/apk/repositories \
    && apk add --no-cache build-base cargo libffi-dev openssl-dev \
    && python -m pip install --no-cache-dir --index-url https://mirrors.aliyun.com/pypi/simple/ uv==0.12.13

WORKDIR /workspace/NutriAthenaAgent
COPY pyproject.toml uv.lock ./
# Export registry dependencies as pinned, hashed requirements. uv.lock contains
# PyPI artifact URLs; installing the export makes uv actually use the mirror.
RUN uv export --locked --offline --no-dev --no-emit-project --no-header --no-annotate \
        --format requirements-txt > /tmp/requirements.txt \
    && python -m venv /opt/nutriathena-venv \
    && uv pip install --python /opt/nutriathena-venv/bin/python --require-hashes \
        --index-url https://mirrors.aliyun.com/pypi/simple/ -r /tmp/requirements.txt

FROM python:3.11-alpine3.22 AS runtime
RUN sed -i 's@dl-cdn.alpinelinux.org@mirrors.aliyun.com@g' /etc/apk/repositories \
    && apk add --no-cache ca-certificates tzdata \
    && addgroup -S nutriathena && adduser -S -G nutriathena nutriathena \
    && mkdir -p /workspace/NutriAthenaAgent/logs \
    && chown nutriathena:nutriathena /workspace/NutriAthenaAgent/logs

ENV PATH="/opt/nutriathena-venv/bin:$PATH" \
    PYTHONPATH="/workspace/NutriAthenaAgent/src" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai
WORKDIR /workspace/NutriAthenaAgent
COPY --from=builder /opt/nutriathena-venv /opt/nutriathena-venv
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY migrations ./migrations
COPY skills ./skills
USER nutriathena
EXPOSE 8101

# Preserve the existing explicit migration CLI; never serve after a failure.
CMD ["/bin/sh", "-c", "python -m nutriathena_agent.main migrate && exec python -m nutriathena_agent.main serve"]
