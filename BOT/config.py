#!/usr/bin/env python3
"""
OPENBOT v3.1 - Configuração Centralizada
Suporte multi-provider: OpenAI, DeepSeek, Groq (todos via openai==0.28.1)
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict

# ============================================================
# PROVIDERS DISPONÍVEIS
# Todos usam a mesma lib openai==0.28.1, só muda api_base + api_key + model
# ============================================================

PROVIDERS: Dict[str, dict] = {
    "openai": {
        "api_base":    "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "models": {
            "default": "gpt-4o-mini",
            "available": ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
        },
        "label": "OpenAI (GPT)"
    },
    "deepseek": {
        "api_base":    "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "models": {
            "default": "deepseek-chat",
            "available": ["deepseek-chat", "deepseek-coder"]
        },
        "label": "DeepSeek"
    },
    "groq": {
        "api_base":    "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "models": {
            "default": "llama-3.1-8b-instant",
            "available": [
                "llama-3.1-8b-instant",
                "llama-3.1-70b-versatile",
                "llama3-8b-8192",
                "mixtral-8x7b-32768",
                "gemma2-9b-it"
            ]
        },
        "label": "Groq (LLaMA / Mixtral)"
    }
}

# ============================================================
# PROVIDER ATIVO — altere aqui ou via env OPENBOT_PROVIDER
# Valores válidos: "openai" | "deepseek" | "groq"
# ============================================================

ACTIVE_PROVIDER_NAME = os.environ.get("OPENBOT_PROVIDER", "deepseek").lower()

if ACTIVE_PROVIDER_NAME not in PROVIDERS:
    print(f"⚠️  Provider '{ACTIVE_PROVIDER_NAME}' inválido. Usando 'deepseek'.")
    ACTIVE_PROVIDER_NAME = "deepseek"

ACTIVE_PROVIDER = PROVIDERS[ACTIVE_PROVIDER_NAME]

# ============================================================
# MODELO ATIVO — altere aqui ou via env OPENBOT_MODEL
# ============================================================

ACTIVE_MODEL = os.environ.get(
    "OPENBOT_MODEL",
    ACTIVE_PROVIDER["models"]["default"]
)

# ============================================================
# API KEY — lida do env correto para o provider ativo
# ============================================================

ACTIVE_API_KEY = os.environ.get(ACTIVE_PROVIDER["api_key_env"], "").strip()

if not ACTIVE_API_KEY:
    print(f"⚠️  {ACTIVE_PROVIDER['api_key_env']} não definida!")
else:
    print(f"✅ {ACTIVE_PROVIDER['label']} | Modelo: {ACTIVE_MODEL} | API Key carregada")


# ============================================================
# CONFIGURAÇÃO DE SEGURANÇA
# ============================================================

@dataclass
class SecurityConfig:
    jwt_secret: str              = os.environ.get("JWT_SECRET", "CHANGE-THIS-IN-PRODUCTION")
    jwt_algorithm: str           = "HS256"
    jwt_expiration_hours: int    = 24
    min_password_length: int     = 8
    require_uppercase: bool      = True
    require_lowercase: bool      = True
    require_digit: bool          = True
    require_special: bool        = True
    max_login_attempts: int      = 5
    lockout_duration_seconds:int = 900
    max_code_executions: int     = 8
    code_timeout_seconds: int    = 15
    session_timeout_seconds: int = 3600


# ============================================================
# CONFIGURAÇÃO DO AGENTE
# ============================================================

@dataclass
class AgentConfig:
    # Provider ativo (preenchido automaticamente)
    provider_name: str  = ACTIVE_PROVIDER_NAME
    api_base: str       = ACTIVE_PROVIDER["api_base"]
    api_key: str        = ACTIVE_API_KEY
    model: str          = ACTIVE_MODEL
    temperature: float  = 0.3
    max_tokens: int     = 2048

    # Limites do agente
    max_agent_steps: int       = 16
    max_tool_executions: int   = 32
    tool_timeout: int          = 900

    # Workers
    thread_pool_workers: int   = 16
    process_pool_workers: int  = 8

    def switch_provider(self, provider_name: str, model: str = None):
        """
        Troca provider em runtime sem reiniciar o servidor.
        Uso: agent_config.switch_provider("groq", "llama-3.1-8b-instant")
        """
        if provider_name not in PROVIDERS:
            raise ValueError(f"Provider '{provider_name}' inválido. Disponíveis: {list(PROVIDERS.keys())}")
        
        p = PROVIDERS[provider_name]
        api_key = os.environ.get(p["api_key_env"], "").strip()
        
        if not api_key:
            raise ValueError(f"{p['api_key_env']} não está definida no ambiente.")
        
        self.provider_name = provider_name
        self.api_base      = p["api_base"]
        self.api_key       = api_key
        self.model         = model or p["models"]["default"]
        
        print(f"🔄 Provider alterado → {p['label']} | Modelo: {self.model}")
        return self


# ============================================================
# CONFIGURAÇÃO DE MEMÓRIA
# ============================================================

@dataclass
class MemoryConfig:
    # Short-term (RAM)
    short_term_size: int        = 30
    short_term_ttl: int         = 3600      # 1 hora

    # Medium-term (sessão RAM)
    medium_term_size: int       = 100
    medium_term_ttl: int        = 86400     # 24 horas

    # Long-term (SQLite)
    long_term_db: str           = "agent_memory.db"

    # Relevância
    min_relevance_score: float  = 0.1
    importance_threshold: float = 0.3

    # Chat history
    max_chat_history: int       = 32       # máx mensagens em RAM por usuário
    chat_history_to_llm: int    = 8      # quantas enviar ao LLM por requisição


# ============================================================
# CONFIGURAÇÃO DO SERVIDOR
# ============================================================

@dataclass
class ServerConfig:
    host: str       = "0.0.0.0"
    port: int       = 5000
    debug: bool     = False
    users_db: str   = "users.db"
    memory_db: str  = "agent_memory_v3.db"
    log_file: str   = "openbot_v3.log"
    log_level: str  = "INFO"
    enable_cors: bool = False


# ============================================================
# CONFIG PRINCIPAL
# ============================================================

class Config:
    def __init__(
        self,
        security: Optional[SecurityConfig] = None,
        agent: Optional[AgentConfig]       = None,
        memory: Optional[MemoryConfig]     = None,
        server: Optional[ServerConfig]     = None
    ):
        self.security = security or SecurityConfig()
        self.agent    = agent    or AgentConfig()
        self.memory   = memory   or MemoryConfig()
        self.server   = server   or ServerConfig()

    def validate(self) -> tuple:
        errors = []
        if not self.agent.api_key:
            errors.append(f"{ACTIVE_PROVIDER['api_key_env']} não definida")
        if not self.server.debug and self.security.jwt_secret == "CHANGE-THIS-IN-PRODUCTION":
            errors.append("JWT_SECRET deve ser alterado em produção")
        if self.agent.max_agent_steps < 1:
            errors.append("max_agent_steps deve ser > 0")
        return len(errors) == 0, errors

    def print_summary(self):
        p = PROVIDERS.get(self.agent.provider_name, {})
        print("=" * 65)
        print("🚀 OPENBOT v3.1 — Configuração")
        print("=" * 65)
        print(f"\n🤖 LLM Provider:")
        print(f"   Provider : {p.get('label', self.agent.provider_name)}")
        print(f"   Modelo   : {self.agent.model}")
        print(f"   API Base : {self.agent.api_base}")
        print(f"   API Key  : {'✅ Configurada' if self.agent.api_key else '❌ Não configurada'}")
        print(f"\n🔐 Segurança:")
        print(f"   JWT Secret : {'✅ OK' if self.security.jwt_secret != 'CHANGE-THIS-IN-PRODUCTION' else '⚠️ Padrão (INSEGURO)'}")
        print(f"   Expiração  : {self.security.jwt_expiration_hours}h")
        print(f"\n🧠 Memória:")
        print(f"   Short-term TTL : {self.memory.short_term_ttl}s ({self.memory.short_term_ttl//3600}h)")
        print(f"   Medium-term TTL: {self.memory.medium_term_ttl}s ({self.memory.medium_term_ttl//3600}h)")
        print(f"   Long-term DB   : {self.memory.long_term_db}")
        print(f"   Threshold      : {self.memory.importance_threshold}")
        print(f"   Chat history   : últimas {self.memory.chat_history_to_llm} msgs ao LLM")
        print(f"\n🌐 Servidor:")
        print(f"   {self.server.host}:{self.server.port}")
        print("=" * 65)

    def list_providers(self):
        """Lista todos os providers disponíveis e seus modelos."""
        print("\n📋 Providers disponíveis:")
        for name, p in PROVIDERS.items():
            key_env   = p["api_key_env"]
            key_ok    = "✅" if os.environ.get(key_env) else "❌"
            active    = " ← ATIVO" if name == self.agent.provider_name else ""
            print(f"\n  {key_ok} {p['label']} [{name}]{active}")
            print(f"     Env key : {key_env}")
            print(f"     Modelos : {', '.join(p['models']['available'])}")


# ============================================================
# CONFIGS PRÉ-DEFINIDAS
# ============================================================

def get_development_config() -> Config:
    return Config(
        security=SecurityConfig(jwt_secret="dev-secret-key", max_login_attempts=10),
        server=ServerConfig(debug=True, enable_cors=True)
    )

def get_production_config() -> Config:
    return Config(
        security=SecurityConfig(
            jwt_secret=os.environ.get("JWT_SECRET", "CHANGE-THIS-IN-PRODUCTION"),
            lockout_duration_seconds=1800
        ),
        server=ServerConfig(debug=False, log_level="WARNING")
    )

def get_testing_config() -> Config:
    return Config(
        security=SecurityConfig(
            jwt_secret="test-secret",
            max_login_attempts=100,
            min_password_length=4,
            require_uppercase=False,
            require_lowercase=False,
            require_digit=False,
            require_special=False
        ),
        agent=AgentConfig(max_agent_steps=5, max_tool_executions=10),
        memory=MemoryConfig(short_term_size=5, long_term_db=":memory:"),
        server=ServerConfig(users_db=":memory:", debug=True)
    )

def load_config_from_env() -> Config:
    env = os.environ.get("OPENBOT_ENV", "development").lower()
    if env == "production":
        return get_production_config()
    elif env == "testing":
        return get_testing_config()
    return get_development_config()


# ============================================================
# TESTE DIRETO
# ============================================================

if __name__ == "__main__":
    cfg = load_config_from_env()
    cfg.print_summary()
    cfg.list_providers()
    is_valid, errors = cfg.validate()
    if is_valid:
        print("\n✅ Configuração válida!")
    else:
        print("\n❌ Erros:")
        for e in errors:
            print(f"   • {e}")
