"""Settings. Everything can be overridden with an environment variable."""

from __future__ import annotations

import os

USER_AGENT = "pagewise/0.1 (+https://github.com/ron1120/pagewise)"

# Where the crawled pages and the vector index live (both are rebuilt by the CLI).
DATA_DIR = os.environ.get("PAGEWISE_DATA_DIR", "data")
PAGES_FILE = os.path.join(DATA_DIR, "pages.json")
INDEX_DIR = os.path.join(DATA_DIR, "index")
COLLECTION = "pagewise"

# Chunking.
CHUNK_CHARS = 900

# Retrieval. Chunks are ranked by 0.7 * vector similarity + 0.3 * keyword overlap.
TOP_K = 4
CANDIDATES = 12
VECTOR_WEIGHT = 0.7
# A question is "not covered" when even its best chunk is weaker than this.
# Tuned against evals/golden.json (see README); change it and re-run `pagewise eval`.
MIN_SCORE = float(os.environ.get("PAGEWISE_MIN_SCORE", "0.28"))

# Model. The model call is skipped entirely when retrieval finds nothing relevant.
MODEL = os.environ.get("PAGEWISE_MODEL", "claude-sonnet-5-5")
EFFORT = os.environ.get("PAGEWISE_EFFORT", "medium")
MAX_TOKENS = 2000
MAX_QUESTION_CHARS = 500
# Opt-in server-side refusal fallback (Claude API only). Off by default.
FALLBACKS = os.environ.get("PAGEWISE_FALLBACKS", "") == "1"
