#!/usr/bin/env python3
"""
Arquivo de configuração centralizado para OPENROKO v2.0
"""

import os
from dataclasses import dataclass
from typing import Optional

# ============================================================
# CONFIGURAÇÕES DE SEGURANÇA
# ============================================================

@dataclass
class SecurityConfig:
    """Configurações de segurança"""
    
    # JWT
    jwt_secret: str = os.environ.get("JWT_SECRET", "CHANGE-THIS-IN-PRODUCTION")
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    
    # Senha
    min_password_length: int = 8
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digit: bool = True
    require_special: bool = True
    
    # Rate Limiting
    max_login_attempts: int = 5
    lockout_duration_seconds: int = 900  # 15 minutos
    
    # Execução de código
    max_code_executions: int = 8
    code_timeout_seconds: int = 15
    
    # Sessões
    session_timeout_seconds: int = 3600  # 1 hora


# ============================================================
# CONFIGURAÇÕES DO AGENTE
# ============================================================

@dataclass
class AgentConfig:
    """Configurações do agente de raciocínio"""
    
    # OpenAI
    openai_api_key: str = os.environ.get("OPENAI_API_KEY", "")
    openai_model: str = "gpt-4o-mini"
    temperature: float = 0.2
    
    # Limites
    max_agent_steps: int = 32
    max_code_executions: int = 8
    
    # Workers
    thread_pool_workers: int = 8
    process_pool_workers: int = 2


# ============================================================
# CONFIGURAÇÕES DE MEMÓRIA
# ============================================================

@dataclass
class MemoryConfig:
    """Configurações do sistema de memória HGR"""
    
    # Short-term
    short_term_size: int = 10
    short_term_ttl: int = 300  # 5 minutos
    
    # Medium-term
    medium_term_size: int = 50
    medium_term_ttl: int = 3600  # 1 hora
    
    # Long-term
    long_term_db: str = "agent_memory.db"
    
    # Relevância
    min_relevance_score: float = 0.3
    importance_threshold: float = 0.6


# ============================================================
# CONFIGURAÇÕES DO SERVIDOR
# ============================================================

@dataclass
class ServerConfig:
    """Configurações do servidor Quart"""
    
    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = False
    
    # Bancos de dados
    users_db: str = "users.db"
    memory_db: str = "agent_memory.db"
    
    # Logs
    log_file: str = "agent_execution.log"
    log_level: str = "INFO"
    
    # CORS (se necessário)
    enable_cors: bool = False
    cors_origins: list = None


# ============================================================
# CONFIGURAÇÃO PRINCIPAL
# ============================================================

class Config:
    """Configuração principal do sistema"""
    
    def __init__(
        self,
        security: Optional[SecurityConfig] = None,
        agent: Optional[AgentConfig] = None,
        memory: Optional[MemoryConfig] = None,
        server: Optional[ServerConfig] = None
    ):
        self.security = security or SecurityConfig()
        self.agent = agent or AgentConfig()
        self.memory = memory or MemoryConfig()
        self.server = server or ServerConfig()
    
    def validate(self) -> tuple[bool, list[str]]:
        """
        Valida a configuração
        Retorna (is_valid, errors)
        """
        errors = []
        
        # Validar OpenAI API Key
        if not self.agent.openai_api_key:
            errors.append("OPENAI_API_KEY não definida")
        
        # Validar JWT Secret em produção
        if not self.server.debug and self.security.jwt_secret == "CHANGE-THIS-IN-PRODUCTION":
            errors.append("JWT_SECRET deve ser alterado em produção")
        
        # Validar limites
        if self.agent.max_agent_steps < 1:
            errors.append("max_agent_steps deve ser > 0")
        
        if self.security.max_code_executions < 1:
            errors.append("max_code_executions deve ser > 0")
        
        return len(errors) == 0, errors
    
    def print_summary(self):
        """Imprime resumo da configuração"""
        print("=" * 60)
        print("OPENROKO v2.0 - Configuração")
        print("=" * 60)
        print(f"\n🔐 Segurança:")
        print(f"  • JWT Secret: {'✅ Configurado' if self.security.jwt_secret != 'CHANGE-THIS-IN-PRODUCTION' else '⚠️ Usar padrão (INSEGURO)'}")
        print(f"  • JWT Expiração: {self.security.jwt_expiration_hours}h")
        print(f"  • Max tentativas login: {self.security.max_login_attempts}")
        print(f"  • Bloqueio: {self.security.lockout_duration_seconds}s")
        
        print(f"\n🤖 Agente:")
        print(f"  • Modelo: {self.agent.openai_model}")
        print(f"  • API Key: {'✅ Configurada' if self.agent.openai_api_key else '❌ Não configurada'}")
        print(f"  • Max steps: {self.agent.max_agent_steps}")
        print(f"  • Max execuções código: {self.agent.max_code_executions}")
        
        print(f"\n🧠 Memória:")
        print(f"  • Short-term: {self.memory.short_term_size} entradas")
        print(f"  • Medium-term: {self.memory.medium_term_size} entradas")
        print(f"  • Long-term DB: {self.memory.long_term_db}")
        print(f"  • Threshold importância: {self.memory.importance_threshold}")
        
        print(f"\n🌐 Servidor:")
        print(f"  • Host: {self.server.host}")
        print(f"  • Porta: {self.server.port}")
        print(f"  • Debug: {self.server.debug}")
        print(f"  • Users DB: {self.server.users_db}")
        print(f"  • Log: {self.server.log_file}")
        
        print("=" * 60)


# ============================================================
# CONFIGURAÇÕES PRÉ-DEFINIDAS
# ============================================================

def get_development_config() -> Config:
    """Configuração para desenvolvimento"""
    return Config(
        security=SecurityConfig(
            jwt_secret="dev-secret-key",
            max_login_attempts=10,  # Mais permissivo
        ),
        agent=AgentConfig(
            max_agent_steps=50,  # Mais steps para testes
        ),
        server=ServerConfig(
            debug=True,
            enable_cors=True,
            cors_origins=["*"]
        )
    )


def get_production_config() -> Config:
    """Configuração para produção"""
    return Config(
        security=SecurityConfig(
            jwt_secret=os.environ.get("JWT_SECRET"),
            max_login_attempts=5,
            lockout_duration_seconds=1800,  # 30 minutos
        ),
        agent=AgentConfig(
            max_agent_steps=32,
        ),
        server=ServerConfig(
            debug=False,
            enable_cors=False,
            log_level="WARNING"
        )
    )


def get_testing_config() -> Config:
    """Configuração para testes"""
    return Config(
        security=SecurityConfig(
            jwt_secret="test-secret",
            max_login_attempts=100,
            min_password_length=4,  # Senhas simples para testes
            require_uppercase=False,
            require_lowercase=False,
            require_digit=False,
            require_special=False,
        ),
        agent=AgentConfig(
            max_agent_steps=10,
            max_code_executions=3,
        ),
        memory=MemoryConfig(
            short_term_size=5,
            long_term_db=":memory:",  # SQLite em memória
        ),
        server=ServerConfig(
            users_db=":memory:",
            debug=True
        )
    )


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def load_config_from_env() -> Config:
    """Carrega configuração das variáveis de ambiente"""
    
    env = os.environ.get("OPENROKO_ENV", "development").lower()
    
    if env == "production":
        return get_production_config()
    elif env == "testing":
        return get_testing_config()
    else:
        return get_development_config()


# ============================================================
# EXEMPLO DE USO
# ============================================================

if __name__ == "__main__":
    # Testar configuração
    config = load_config_from_env()
    
    # Validar
    is_valid, errors = config.validate()
    
    if is_valid:
        config.print_summary()
        print("\n✅ Configuração válida!")
    else:
        print("\n❌ Erros na configuração:")
        for error in errors:
            print(f"  • {error}")
