"""Web server: a small chat page and a JSON API.

Because a public endpoint spends the owner's API credit, every client IP is limited to a few questions a minute.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .answer import ask
from .config import MAX_QUESTION_CHARS
from .llm import Judge
from .store import Index

WEB_DIR = Path(__file__).parent / "web"
RATE_LIMIT = int(os.environ.get("PAGEWISE_RATE_LIMIT", "10"))  # questions per IP per minute
WINDOW = 60.0


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


def create_app(index: Index, judge: Judge, rate_limit: int = RATE_LIMIT) -> FastAPI:
    app = FastAPI(title="pagewise", docs_url=None, redoc_url=None)

    origins = [o.strip() for o in os.environ.get("PAGEWISE_CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["POST", "GET"], allow_headers=["Content-Type"])

    recent: dict[str, deque[float]] = defaultdict(deque)

    def check_rate(ip: str) -> None:
        now = time.monotonic()
        q = recent[ip]
        while q and now - q[0] > WINDOW:
            q.popleft()
        if len(q) >= rate_limit:
            raise HTTPException(status_code=429, detail="Too many questions. Please wait a minute.")
        q.append(now)

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return (WEB_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "chunks": index.count()}

    @app.post("/api/ask")
    def api_ask(body: AskRequest, request: Request) -> dict:
        check_rate(request.client.host if request.client else "unknown")
        try:
            return ask(body.question, index, judge).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app
