FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the embedding model while building, so the container starts without needing the internet.
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction as D; D()(['warm up'])"

COPY pagewise ./pagewise
COPY evals ./evals
COPY data ./data
COPY docker-entrypoint.sh .

# Run as a normal user. Its home holds the embedding model cache; /app/data holds the pages and the index.
RUN useradd --create-home pagewise \
    && mkdir -p /home/pagewise/.cache && cp -r /root/.cache/chroma /home/pagewise/.cache/chroma \
    && chown -R pagewise /app /home/pagewise
USER pagewise

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

ENTRYPOINT ["./docker-entrypoint.sh"]
