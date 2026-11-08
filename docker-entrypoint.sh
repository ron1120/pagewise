#!/bin/sh
# Builds the knowledge base on start, then serves the chat page and API.
#   PAGEWISE_DOCS_DIR + PAGEWISE_DOCS_BASE_URL   read a project folder (mount it read-only)
#   PAGEWISE_DOCS_CODE=1                         ...and read its code and config files too, not just Markdown
#   PAGEWISE_SITE_URL                            crawl a website
#   (neither)                                    use the demo site snapshot that ships in the image
set -e

if [ -n "$PAGEWISE_DOCS_DIR" ]; then
  CODE_FLAG=""
  [ "$PAGEWISE_DOCS_CODE" = "1" ] && CODE_FLAG="--code"
  python -m pagewise docs "$PAGEWISE_DOCS_DIR" --base-url "${PAGEWISE_DOCS_BASE_URL:?set PAGEWISE_DOCS_BASE_URL to the URL the docs are published at}" $CODE_FLAG
elif [ -n "$PAGEWISE_SITE_URL" ]; then
  python -m pagewise crawl "$PAGEWISE_SITE_URL"
fi
python -m pagewise index

exec python -m pagewise serve --host 0.0.0.0 --port 8000
