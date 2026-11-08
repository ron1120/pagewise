# pagewise

Ask questions about a website and get answers **only from its own pages**, each with the pages it came from.
If the site doesn't say, pagewise says so instead of guessing.

It crawls a site, indexes the text, and answers through retrieval plus Claude. The "never guess" rule is enforced
by the code around the model, not just by a line in the prompt.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

python -m pagewise crawl https://ron-shitrit.pages.dev   # download the pages -> data/pages.json
python -m pagewise index                                 # chunk + embed them  -> data/index

export ANTHROPIC_API_KEY=...                             # only needed for ask / chat / serve / eval --live
python -m pagewise ask "What does the CI triage agent do?"
python -m pagewise chat                                  # interactive, in the terminal
python -m pagewise serve                                 # chat page at http://127.0.0.1:8000
```

The repo ships a snapshot of the demo site in `data/pages.json`, so `index` works without crawling.
The first `index` downloads a small embedding model (about 80 MB) that runs locally.

## How a question is answered

1. **Retrieve.** Candidates come from two searches: nearest chunks by meaning (ChromaDB vectors) and best matches by
   exact words (keywords). Each candidate is scored `0.7 * vector similarity + 0.3 * keyword overlap`.
2. **Gate.** If even the best chunk scores below `0.28`, the question is off-topic for this site. pagewise answers
   "I can't answer that from this site's pages." and **never calls the model**.
3. **Judge.** Otherwise Claude receives the top 4 chunks as numbered sources and must return JSON:
   `{answerable, answer, source_ids}`. It is told to use only the sources, to say `answerable: false` when they
   don't contain the answer, and to treat both the sources and the question as untrusted text.
4. **Verify.** The answer is rejected (shown as "couldn't produce a reliable answer") if it cites no source, cites
   an id it wasn't given, or states a number that none of the cited sources contain.
5. **Respond.** The answer comes back with the cited pages: title, section and link.

If the model is unavailable, refuses, runs out of tokens or returns something unreadable, the visitor gets a visible
"couldn't produce a reliable answer" message, never silence and never a guess.

## Guards, and what each one is for

| Guard | Where | Stops |
|---|---|---|
| Not-covered gate | `retrieve.py`, `answer.py` | Off-topic questions reaching the model (and costing money) |
| "Answerable" flag + strict system prompt | `llm.py` | Answering from outside knowledge |
| Citation check | `answer.py` | Answers with no source, or invented source ids |
| Number check | `answer.py` | Invented figures, prices, dates |
| Untrusted-text rule | `llm.py` | Instructions hidden in page text or in the question |
| Question length limit, per-IP rate limit | `server.py` | Abuse of a public endpoint that spends API credit |
| `textContent` only in the chat page | `web/index.html` | Answers being interpreted as HTML |

## Evaluation

`evals/golden.json` holds 28 questions about the demo site: 18 answerable from one page, 6 off-topic (must be
refused before the model), 4 on-topic but not on the site (the model must decline).

```bash
python -m pagewise eval          # offline: retrieval + gate, no API key needed (this runs in CI)
python -m pagewise eval --live   # full pipeline with Claude: right page cited, expected facts present, refusals honoured
```

**What is measured:** offline, 28/28 pass. For the 18 answerable questions the right page is in the top 4, and every
off-topic question scores at most 0.21 against a gate of 0.28, while the weakest answerable one scores 0.43.

**What is not measured yet:**
- **The live path has not been run against the real API.** The tests exercise the request and the answer checks with a
  fake model, so the shape of the call and every refusal path is covered, but accuracy with Claude is untested until
  `pagewise eval --live` has been run.
- The gate threshold was tuned on the same 28 questions it is scored on. Treat 28/28 as "works on the demo set", not as
  a general accuracy figure.
- Only one site (a small portfolio) has been tried.

## Known limits

- Retrieval can miss when a page's text is only an unlabeled list. "What technologies does Ron work with?" finds the
  skills list; "what is Ron's tech stack?" does not.
- Keyword search scans every chunk on each question. That is fine for a site of hundreds of pages, not for a huge corpus.
- It reads static HTML. Pages that only exist after JavaScript runs are not crawled.
- Each question is answered on its own: no memory of the conversation.
- The rate limit is in memory, per process.
- The default model is `claude-sonnet-5-5`. Set `PAGEWISE_MODEL` to try another one (for example `claude-opus-5-5`), and re-run the live eval after
  changing it.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | | Needed for ask, chat, serve and `eval --live` |
| `PAGEWISE_MODEL` | `claude-sonnet-5-5` | Model that writes the answer |
| `PAGEWISE_EFFORT` | `medium` | Model effort level |
| `PAGEWISE_MIN_SCORE` | `0.28` | The not-covered gate |
| `PAGEWISE_RATE_LIMIT` | `10` | Questions per IP per minute on the web server |
| `PAGEWISE_CORS_ORIGINS` | none | Comma-separated origins allowed to call the API from a browser |
| `PAGEWISE_FALLBACKS` | off | Set to `1` to opt into server-side refusal fallback |
| `PAGEWISE_SOURCE_NAME` | `this site's pages` | How refusals name the source, e.g. `the project docs` |
| `PAGEWISE_EXAMPLES` | portfolio examples | Example questions on the chat page, separated by `\|` |
| `PAGEWISE_DATA_DIR` | `data` | Where pages and the index live |
| `PAGEWISE_EMBEDDER` | local model | `hash` uses a tiny offline embedder (tests and smoke runs) |

## Using it on documentation, in Docker

pagewise can read a folder of Markdown files instead of crawling a site, and it ships a Dockerfile, so it can run as
the help assistant of another project:

```bash
python -m pagewise docs ./my-project --base-url https://github.com/me/my-project/blob/main   # one page per .md file
python -m pagewise index
```

```bash
docker build -t pagewise .
docker run -p 8010:8000 -e ANTHROPIC_API_KEY \
  -e PAGEWISE_DOCS_DIR=/docs -e PAGEWISE_DOCS_BASE_URL=https://github.com/me/my-project/blob/main \
  -v "$PWD/my-project:/docs:ro" pagewise
```

The entrypoint builds the index when the container starts, then serves the chat page and `POST /api/ask`. Citations
link to `--base-url` plus the file path. The chat page uses relative URLs, so it also works behind a proxy path such
as `/assistant/`. A working example is the Task Manager app's `docker-compose.yml`
(`github.com/ron1120/task-manager-infrastructure`), where it is the `pagewise` service.

## Crawling politely

The crawler honours `robots.txt`, stays on one host, identifies itself with a `pagewise` user agent, waits between
requests, follows the sitemap when there is one, and stops at `--max-pages`.

## Layout

```
pagewise/crawl.py      fetch pages, extract readable text grouped under headings
pagewise/docs.py       read Markdown files as pages (for documentation)
pagewise/chunk.py      split into small chunks that remember their page and section
pagewise/store.py      ChromaDB index + swappable embedders
pagewise/retrieve.py   hybrid search, scoring and the not-covered gate
pagewise/llm.py        the Claude call: structured JSON verdict
pagewise/answer.py     the pipeline and its verification checks
pagewise/evals.py      golden-question runner (offline and live)
pagewise/server.py     FastAPI app, rate limit, chat page
pagewise/cli.py        crawl, docs, index, ask, chat, serve, eval
evals/golden.json      the 28 golden questions
tests/                 51 offline tests (fake site, fake model, no network)
```

## Roadmap

1. Run and publish the live eval, then pick the cheapest model that holds it.
2. Streaming answers in the chat page.
3. Conversation memory for follow-up questions.
4. Incremental re-crawl of only changed pages.
5. A second sample site, to show it is not tuned to one.
