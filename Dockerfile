FROM python:3.11-slim AS sandbox-rootfs

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash ca-certificates chromium fonts-dejavu-core poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY sandbox/requirements.txt /tmp/sandbox-requirements.txt
RUN pip install --no-cache-dir -r /tmp/sandbox-requirements.txt \
    && rm /tmp/sandbox-requirements.txt

WORKDIR /workspace


FROM debian:trixie-slim AS sandbox-archive

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates umoci \
    && rm -rf /var/lib/apt/lists/*
RUN umoci init --layout /oci \
    && umoci new --image /oci:sandbox \
    && umoci unpack --image /oci:sandbox /bundle
COPY --from=sandbox-rootfs / /bundle/rootfs/
RUN umoci repack --image /oci:sandbox /bundle \
    && tar -C /oci -cf /sandbox.tar . \
    && sha256sum /sandbox.tar | cut -d ' ' -f1 > /sandbox.sha256


FROM sandbox-rootfs

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=sandbox-archive /sandbox.tar /opt/contraponto-sandbox/sandbox.tar
COPY --from=sandbox-archive /sandbox.sha256 /opt/contraponto-sandbox/sandbox.sha256

RUN mkdir -p /app/workdirs \
    && chmod 755 /app/docker-entrypoint.sh \
    && chown -R appuser:appuser /app

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
