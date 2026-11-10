"""Command line: crawl, docs, index, ask, chat, serve, eval."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .answer import ANSWERED, ask
from .build import build_index, load_pages, open_index, save_pages
from .config import INDEX_DIR, PAGES_FILE
from .crawl import crawl
from .docs import load_repo
from .evals import load_golden, report, run_evals
from .llm import ClaudeJudge


def _print_answer(answer, as_json: bool) -> None:
    if as_json:
        print(json.dumps(answer.to_dict(), indent=2, ensure_ascii=False))
        return
    print(answer.text)
    if answer.status == ANSWERED:
        print()
        for s in answer.sources:
            print(f"  [{s.n}] {s.title} > {s.heading}\n      {s.url}")
    usage = answer.usage
    if usage["calls"] == 0:
        print("\n(refused before the model: no cost)")
    else:
        price = "cost unknown" if answer.cost_usd is None else f"about ${answer.cost_usd:.4f}"
        print(f"\n({usage['calls']} model call(s), {usage['input_tokens']} tokens in, {usage['output_tokens']} out, {price})")


def cmd_crawl(args) -> int:
    pages = crawl(args.url, max_pages=args.max_pages, delay=args.delay, under_start_path=args.under_start_path, exclude=tuple(args.exclude))
    save_pages(pages, args.out)
    print(f"Crawled {len(pages)} pages -> {args.out}")
    for p in pages:
        print(f"  {p.url}  ({len(p.sections)} sections)")
    return 0 if pages else 1


def cmd_docs(args) -> int:
    pages = load_repo(args.directory, args.base_url, include_code=args.code)
    save_pages(pages, args.out)
    print(f"Read {len(pages)} pages from {args.directory} -> {args.out}")
    files = sorted({p.url.split("#")[0] for p in pages})
    for f in files:
        print(f"  {f}")
    return 0 if pages else 1


def cmd_index(args) -> int:
    index = build_index(load_pages(args.pages), args.index)
    print(f"Indexed {index.count()} chunks -> {args.index}")
    return 0


def cmd_ask(args) -> int:
    answer = ask(" ".join(args.question), open_index(args.index), ClaudeJudge())
    _print_answer(answer, args.json)
    return 0


def cmd_chat(args) -> int:
    index, judge = open_index(args.index), ClaudeJudge()
    print("Ask about the site. Empty line to quit.")
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not question:
            return 0
        try:
            _print_answer(ask(question, index, judge), as_json=False)
        except ValueError as exc:
            print(exc)


def cmd_serve(args) -> int:
    import uvicorn

    from .server import create_app

    uvicorn.run(create_app(open_index(args.index), ClaudeJudge()), host=args.host, port=args.port)
    return 0


def cmd_eval(args) -> int:
    index = open_index(args.index)
    judge = ClaudeJudge() if args.live else None
    print(f"Mode: {'live (calls Claude)' if args.live else 'offline (retrieval only)'}\n")
    return report(run_evals(load_golden(args.golden), index, judge))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pagewise", description="Answer questions about a website, only from its own pages.")
    parser.add_argument("--version", action="version", version=f"pagewise {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("crawl", help="download a site's pages")
    p.add_argument("url")
    p.add_argument("--max-pages", type=int, default=60)
    p.add_argument("--delay", type=float, default=0.3, help="seconds between requests")
    p.add_argument("--under-start-path", action="store_true", help="stay inside the start URL's folder (for versioned docs)")
    p.add_argument("--exclude", action="append", default=[], metavar="FRAGMENT", help="skip URLs whose path contains this (repeatable)")
    p.add_argument("--out", default=PAGES_FILE)
    p.set_defaults(func=cmd_crawl)

    p = sub.add_parser("docs", help="read a project folder (Markdown, and with --code its code) instead of crawling a site")
    p.add_argument("directory")
    p.add_argument("--code", action="store_true", help="also read code and config files, in windows of about 30 lines")
    p.add_argument("--base-url", required=True, help="URL that the folder is published at, used for citations")
    p.add_argument("--out", default=PAGES_FILE)
    p.set_defaults(func=cmd_docs)

    p = sub.add_parser("index", help="chunk the crawled pages and build the vector index")
    p.add_argument("--pages", default=PAGES_FILE)
    p.add_argument("--index", default=INDEX_DIR)
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("ask", help="ask one question")
    p.add_argument("question", nargs="+")
    p.add_argument("--json", action="store_true")
    p.add_argument("--index", default=INDEX_DIR)
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("chat", help="interactive chat in the terminal")
    p.add_argument("--index", default=INDEX_DIR)
    p.set_defaults(func=cmd_chat)

    p = sub.add_parser("serve", help="run the web chat page and API")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--index", default=INDEX_DIR)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("eval", help="run the golden questions")
    p.add_argument("--golden", default="evals/golden.json")
    p.add_argument("--live", action="store_true", help="call Claude (needs ANTHROPIC_API_KEY)")
    p.add_argument("--index", default=INDEX_DIR)
    p.set_defaults(func=cmd_eval)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
