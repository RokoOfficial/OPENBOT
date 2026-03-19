#!/usr/bin/env python3
"""Helpers for resilient SSE streaming."""

import asyncio
import json
from typing import AsyncIterator, Dict


def sse_event(payload: Dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def stream_text_chunks(text: str, chunk_size: int = 24, delay: float = 0.0) -> AsyncIterator[Dict]:
    if not text:
        return
    for index in range(0, len(text), chunk_size):
        yield {"type": "chunk", "chunk": text[index:index + chunk_size]}
        if delay > 0:
            await asyncio.sleep(delay)
