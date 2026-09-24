FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# bubblewrap fornece a segunda camada de isolamento usada por execute_bash.
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash bubblewrap ca-certificates chromium poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/workdirs \
    && chmod 755 /app/docker-entrypoint.sh \
    && chown -R appuser:appuser /app

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
