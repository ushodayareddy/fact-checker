from __future__ import annotations

import hashlib
from typing import Protocol

from ..models import Evidence


class SourceAdapter(Protocol):
    name: str

    def available(self) -> bool:
        """False when a required API key / config is missing; the retriever skips such adapters."""

    async def search(self, query: str, lang: str, claim_id: str) -> list[Evidence]: ...


def evidence_id(source: str, url: str) -> str:
    return f"{source}:{hashlib.sha1(url.encode()).hexdigest()[:10]}"
