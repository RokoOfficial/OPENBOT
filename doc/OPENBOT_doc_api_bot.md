
# 🔌 Referência da API - OpenBot

## Visão Geral da API

O OpenBot é um sistema de IA modular, aberto e programável. Esta documentação descreve os endpoints, métodos e estruturas de dados para integração programática.

## Base URL
https://seu-openbot.com/api

## Autenticação

OpenBot utiliza tokens de API configurados via variável de ambiente:

OPENBOT_API_KEY=sk-...

## Endpoints Principais

### 1. Chat/Conversação

POST /api/chat
Processa uma solicitação de chat pelo OpenBot.

Request Body:
{
  "message": "Sua pergunta aqui",
  "user_id": "opcional_user_id",
  "context": {
    "conversation_id": "opcional_conversation_id",
    "preferences": {
      "response_style": "detailed|brief|technical",
      "include_sources": true|false
    }
  }
}

Response:
{
  "status": "success|error",
  "response": "Resposta do OpenBot",
  "metadata": {
    "processing_time": 2.5,
    "agents_used": ["default_llm"],
    "memory_entries_retrieved": 0,
    "confidence_score": 0.85
  },
  "execution_log": [
    "🎯 Iniciando processamento do prompt",
    "✅ Resposta gerada"
  ]
}

Códigos de Status:
- 200: Sucesso
- 400: Solicitação inválida
- 401: Não autorizado
- 429: Limite de requisições excedido
- 500: Erro interno do servidor

### 2. Memória

OpenBot possui memória básica para contexto de conversação, sem sistema cognitivo avançado.

GET /api/memory/search
Busca memórias anteriores.

Query Parameters:
?query=texto_da_busca&limit=5

Response:
{
  "status": "success",
  "results": [
    {
      "id": 1,
      "timestamp": "2025-01-20T12:00:00Z",
      "user_prompt": "Pergunta anterior",
      "bot_response": "Resposta guardada"
    }
  ],
  "total_found": 1
}

POST /api/memory/save
Salva interações no histórico do bot.

Request Body:
{
  "user_prompt": "Texto do usuário",
  "bot_response": "Resposta do bot"
}

### 3. Agentes

OpenBot usa agentes simples e LLMs integrados, sem paralelismo avançado.

GET /api/agents/status
Status dos agentes do sistema.

Response:
{
  "agents": {
    "default_llm": {
      "status": "active",
      "capabilities": ["chat"],
      "last_used": "2025-08-23T09:00:00Z",
      "success_rate": 0.90
    }
  }
}

### 4. Sistema

GET /api/system/health
Verificação de saúde do sistema.

Response:
{
  "status": "healthy|degraded|unhealthy",
  "components": {
    "database": "connected",
    "openai_api": "connected"
  },
  "performance": {
    "avg_response_time": 3.0,
    "requests_per_minute": 10,
    "error_rate": 0.05
  },
  "version": "1.0.0",
  "uptime": "2d 4h 15m"
}

GET /api/system/metrics
Métricas detalhadas.

Response:
{
  "requests": {
    "total": 1000,
    "success": 950,
    "errors": 50,
    "avg_processing_time": 3.2
  }
}

## Estruturas de Dados

Interaction Object:
{
  "id": 1,
  "timestamp": "2025-01-20T12:00:00Z",
  "user_prompt": "Pergunta do usuário",
  "bot_response": "Resposta do bot"
}

Error Response:
{
  "status": "error",
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Descrição do erro"
  },
  "request_id": "req_123456789"
}

## Códigos de Erro

| Código | Descrição | Ação Sugerida |
|--------|-----------|---------------|
| INVALID_REQUEST | Solicitação mal formada | Corrigir JSON |
| MISSING_PARAMETER | Parâmetro ausente | Adicionar parâmetro |
| AGENT_UNAVAILABLE | Agente indisponível | Tentar mais tarde |
| MEMORY_ERROR | Erro no histórico | Reportar |
| RATE_LIMIT_EXCEEDED | Limite excedido | Aguardar |
| INTERNAL_ERROR | Erro interno | Contatar suporte |

## Rate Limiting

Limites Padrão:
- Chat API: 30 requisições/minuto por usuário
- Memory API: 60 requisições/minuto por usuário
- System API: 20 requisições/minuto por usuário

Headers de Rate Limit:
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 25
X-RateLimit-Reset: 1642694400

## Exemplos de Uso

1. Chat Simples:
curl -X POST https://seu-openbot.com/api/chat -H "Content-Type: application/json" -d '{"message": "Explique o que é inteligência artificial"}'

2. Buscar Memória:
curl -X GET "https://seu-openbot.com/api/memory/search?query=machine+learning&limit=3"

3. Status do Sistema:
curl -X GET https://seu-openbot.com/api/system/health

## Conclusão

OpenBot é um sistema aberto, modular e simples, voltado para experimentação e integração básica, com foco em chat e memória limitada. Ele não possui paralelismo avançado, memória cognitiva complexa ou protocolos de comunicação próprios como o ROKO.
