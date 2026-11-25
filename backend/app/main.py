from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .config import get_settings
from .languages import load_languages
from .llm import OllamaClient
from .pipeline import Pipeline

MAX_INPUT_CHARS = 10_000


class CheckRequest(BaseModel):
    input: str = Field(min_length=1, max_length=MAX_INPUT_CHARS, description="Claim text or an article URL")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.llm = OllamaClient()
    app.state.pipeline = Pipeline(app.state.llm)
    yield
    await app.state.llm.aclose()


app = FastAPI(title="Indian-language Fact Checker", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    s = get_settings()
    ollama = await app.state.llm.health()
    wanted = {s.reasoning_model, s.embedding_model}
    # Ollama reports untagged models as "name:latest", so a configured "bge-m3" matches "bge-m3:latest".
    installed = set(ollama["models"])
    present = lambda m: m in installed or (":" not in m and f"{m}:latest" in installed)  # noqa: E731
    missing = sorted(m for m in wanted if not present(m)) if ollama["ok"] else sorted(wanted)
    return {
        "ok": ollama["ok"] and not missing,
        "ollama": ollama["ok"],
        "missing_models": missing,
        "models": {"reasoning_model": s.reasoning_model, "embedding_model": s.embedding_model},
    }


@app.get("/api/languages")
async def languages():
    return [lang.model_dump() for lang in load_languages().values()]


@app.post("/api/check")
async def check(req: CheckRequest):
    text = req.input.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Input is empty.")

    async def events():
        async for item in app.state.pipeline.stream(text):
            yield {"event": item["event"], "data": json.dumps(item["data"], ensure_ascii=False)}

    return EventSourceResponse(events())
