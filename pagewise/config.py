"""Settings. Everything can be overridden with an environment variable."""

from __future__ import annotations

import os

USER_AGENT = "pagewise/0.1 (+https://github.com/rronss/pagewise)"

# Where the crawled pages and the vector index live (both are rebuilt by the CLI).
DATA_DIR = os.environ.get("PAGEWISE_DATA_DIR", "data")
PAGES_FILE = os.path.join(DATA_DIR, "pages.json")
INDEX_DIR = os.path.join(DATA_DIR, "index")
COLLECTION = "pagewise"

# How the knowledge base is named in refusals: "I can't answer that from <SOURCE_NAME>."
SOURCE_NAME = os.environ.get("PAGEWISE_SOURCE_NAME", "this site's pages")

# Chunking.
CHUNK_CHARS = 900

# Retrieval. Chunks are ranked by 0.7 * vector similarity + 0.3 * keyword overlap.
TOP_K = int(os.environ.get("PAGEWISE_TOP_K", "4"))  # passages sent to the model
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


# USD per million tokens (input, output). These are Anthropic's published prices for each model, used only to ESTIMATE
# what an answer cost. Check the current price list before quoting a figure, and add a model here to price it.
PRICES = {
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-fable-5-1": (10.00, 50.00),
    "claude-haiku-5-5": (0.10, 0.50),  # for prompts up to 100K tokens
}


def cost_usd(model: str | None, input_tokens: int, output_tokens: int) -> float | None:
    """Estimated cost in dollars, or None when the model is not in PRICES."""
    if model not in PRICES:
        return None
    per_input, per_output = PRICES[model]
    return (input_tokens * per_input + output_tokens * per_output) / 1_000_000
