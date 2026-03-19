#!/usr/bin/env python3
"""
OPENBOT - Configuração compartilhada da aplicação.

Este módulo centraliza:
- providers suportados;
- leitura de variáveis de ambiente;
- configuração de CORS;
- defaults de host/porta/modelo.
"""

import os
from typing import List

from core.providers import PROVIDERS

DEFAULT_PROVIDER_NAME = "deepseek"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5000


def load_local_env() -> None:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    env_path = os.path.join(project_root, ".env")

    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_local_env()


def get_active_provider_name() -> str:
    provider_name = os.environ.get("OPENBOT_PROVIDER", DEFAULT_PROVIDER_NAME).lower()
    if provider_name not in PROVIDERS:
        return DEFAULT_PROVIDER_NAME
    return provider_name


def get_active_provider() -> dict:
    return PROVIDERS[get_active_provider_name()]


def get_active_model() -> str:
    provider = get_active_provider()
    return os.environ.get("OPENBOT_MODEL", provider["models"]["default"])


def get_active_api_key() -> str:
    provider = get_active_provider()
    return os.environ.get(provider["api_key_env"], "").strip()


def get_server_host() -> str:
    return os.environ.get("HOST", DEFAULT_HOST)


def get_server_port() -> int:
    try:
        return int(os.environ.get("PORT", DEFAULT_PORT))
    except ValueError:
        return DEFAULT_PORT


def get_cors_origins() -> List[str]:
    raw_origins = os.environ.get("CORS_ORIGINS", "*").strip()
    if not raw_origins or raw_origins == "*":
        return ["*"]
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
