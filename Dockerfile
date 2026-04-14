# Canton MCP Server - Development Dockerfile
# Uses Python 3.12 with uv for fast dependency management

FROM python:3.12-slim AS builder

# Install git for cloning documentation repositories
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files and README (needed by hatchling build)
COPY pyproject.toml uv.lock README.md ./

# Clone documentation repositories BEFORE copying src/ so source changes
# don't invalidate this expensive layer (~5 min git clone + indexing)
RUN mkdir -p /app/docs && \
    git clone --depth 1 https://github.com/digital-asset/daml.git /app/docs/daml && \
    git clone --depth 1 https://github.com/digital-asset/canton.git /app/docs/canton && \
    git clone --depth 1 https://github.com/digital-asset/daml-finance.git /app/docs/daml-finance

# Copy source code (needed for editable install)
COPY src/ ./src/

# Install dependencies
RUN uv sync --frozen --no-dev

# Pre-download ChromaDB ONNX embedding model (79MB)
# Avoids 79MB download on first request at runtime
# Must call ef() with text — constructor alone is lazy in chromadb 1.x
# HOME must be explicit so Path.home() resolves to /root under uv
RUN HOME=/root uv run python -c "from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2; ONNXMiniLM_L6_V2()(['warmup'])"

# Pre-build ChromaDB index from cloned docs (avoids OOM spike on first request at runtime)
RUN HOME=/root CANONICAL_DOCS_PATH=/app/docs CHROMA_PERSIST_DIR=/app/chroma_db \
    OMP_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false \
    uv run python -c "\
from canton_mcp_server.core.direct_file_loader import DirectFileResourceLoader; \
from canton_mcp_server.core.semantic_search import create_semantic_search; \
from pathlib import Path; \
loader = DirectFileResourceLoader(Path('/app/docs')); \
resources = loader.scan_repositories(); \
all_res = [r for cat in resources.values() for r in cat]; \
search = create_semantic_search(raw_resources=all_res, force_reindex=True); \
stats = search.get_stats() if search else {}; \
print(f'Indexed {stats.get(\"indexed_count\", 0)} resources into /app/chroma_db') \
"

# Final stage
FROM python:3.12-slim

# Service needs git
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*
    
# Install uv in final stage
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create non-root user
RUN useradd -m -u 1000 canton && \
    mkdir -p /app && \
    chown -R canton:canton /app

WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder --chown=canton:canton /app/.venv /app/.venv

# Copy documentation repositories from builder
COPY --from=builder --chown=canton:canton /app/docs /app/docs

# Copy pre-downloaded ONNX model from builder (avoids 79MB download at runtime)
COPY --from=builder --chown=canton:canton /root/.cache/chroma /home/canton/.cache/chroma

# Copy pre-built ChromaDB index from builder (avoids OOM spike on first request)
COPY --from=builder --chown=canton:canton /app/chroma_db /app/chroma_db

# Copy application code
COPY --chown=canton:canton pyproject.toml uv.lock README.md ./
COPY --chown=canton:canton src/ ./src/
COPY --chown=canton:canton schemas/ ./schemas/

# Switch to non-root user
USER canton

# Set Python path to use virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src:$PYTHONPATH"

# Expose MCP server port
EXPOSE 7284

# Readiness check — verifies LLM model and ChromaDB, not just HTTP 200
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7284/ready').read()" || exit 1

# Default command
CMD ["canton-mcp-server"]

