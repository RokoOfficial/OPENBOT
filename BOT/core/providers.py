#!/usr/bin/env python3
"""Provider registry and LLM invocation helpers."""

import asyncio
import os
from typing import Dict, List, Tuple

PROVIDERS: Dict[str, dict] = {
    "openai": {
        "api_base": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "models": {
            "default": "gpt-4o-mini",
            "available": ["gpt-4o-mini", "gpt-4o"],
        },
        "label": "OpenAI (GPT)",
        "transport": "openai_compat",
    },
    "deepseek": {
        "api_base": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "models": {
            "default": "deepseek-chat",
            "available": ["deepseek-chat", "deepseek-coder"],
        },
        "label": "DeepSeek",
        "transport": "openai_compat",
    },
    "anthropic": {
        "api_base": "https://api.anthropic.com/v1/messages",
        "api_key_env": "ANTHROPIC_API_KEY",
        "models": {
            "default": "claude-3-5-haiku-latest",
            "available": [
                "claude-3-5-haiku-latest",
                "claude-3-7-sonnet-latest",
            ],
        },
        "label": "Anthropic (Claude)",
        "transport": "anthropic",
    },
}


def get_provider(provider_name: str) -> dict:
    if provider_name not in PROVIDERS:
        raise ValueError(f"Provider inválido. Disponíveis: {list(PROVIDERS.keys())}")
    return PROVIDERS[provider_name]


def get_api_key(provider_name: str) -> str:
    provider = get_provider(provider_name)
    return os.environ.get(provider["api_key_env"], "").strip()


def _openai_compat_sync(messages: List[dict], provider_name: str, model: str, api_key: str):
    import openai

    provider = get_provider(provider_name)
    openai.api_key = api_key
    openai.api_base = provider["api_base"]
    return openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=0.3,
        max_tokens=2048,
    )


def _split_anthropic_messages(messages: List[dict]) -> Tuple[str, List[dict]]:
    system_parts: List[str] = []
    anthropic_messages: List[dict] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if role == "system":
            system_parts.append(content)
            continue
        if role not in {"user", "assistant"}:
            role = "user"
        anthropic_messages.append({"role": role, "content": content})
    return "\n\n".join(system_parts), anthropic_messages


async def _call_anthropic(messages: List[dict], model: str, api_key: str) -> str:
    import aiohttp

    system_prompt, anthropic_messages = _split_anthropic_messages(messages)
    payload = {
        "model": model,
        "max_tokens": 2048,
        "temperature": 0.3,
        "messages": anthropic_messages or [{"role": "user", "content": "ok"}],
    }
    if system_prompt:
        payload["system"] = system_prompt

    headers = {
        "content-type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(PROVIDERS["anthropic"]["api_base"], headers=headers, json=payload) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                error_text = data.get("error", {}).get("message") or str(data)
                raise RuntimeError(error_text)
            blocks = data.get("content", [])
            text_parts = [block.get("text", "") for block in blocks if block.get("type") == "text"]
            return "".join(text_parts).strip()


async def call_llm(messages: List[dict], provider_name: str, model: str, api_key: str, executor) -> str:
    provider = get_provider(provider_name)
    if not api_key:
        raise RuntimeError(f"{provider['api_key_env']} não definida no ambiente.")

    if provider["transport"] == "anthropic":
        return await _call_anthropic(messages, model, api_key)

    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        executor,
        lambda: _openai_compat_sync(messages, provider_name, model, api_key),
    )
    return response["choices"][0]["message"]["content"].strip()
