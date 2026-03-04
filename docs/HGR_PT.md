# HGR v4.0 — Hierarchical Grounded Reasoning
## Sistema de Memória Persistente para Agentes Cognitivos · OPENBOT

> **Versão:** 4.0 · **Licença:** Open-Source · **Runtime:** Python 3.10+ · **Banco de dados:** SQLite (WAL)

---

## Índice

1. [Visão Geral](#visão-geral)
2. [Arquitetura Central](#arquitetura-central)
3. [Esquema do Banco de Dados](#esquema-do-banco-de-dados)
4. [Componentes](#componentes)
5. [Referência da API Pública](#referência-da-api-pública)
6. [Parâmetros de Configuração](#parâmetros-de-configuração)
7. [Fluxo de Dados](#fluxo-de-dados)
8. [Integração com o OPENBOT](#integração-com-o-openbot)
9. [Endpoints REST](#endpoints-rest)
10. [Extração Automática de Factos](#extração-automática-de-factos)
11. [Agendamento Cron](#agendamento-cron)
12. [Início Rápido](#início-rápido)
13. [Melhorias em relação à v3.1](#melhorias-em-relação-à-v31)

---

## Visão Geral

**HGR** (Hierarchical Grounded Reasoning) é o subsistema de memória persistente do OPENBOT v4.0. Equipa o agente com três camadas de memória complementares — uma cache RAM de curto prazo, um armazenamento de sessão em memória e uma camada de persistência SQLite de longo prazo — todas orquestradas por um único ficheiro de base de dados unificado (`agent_memory.db`).

Garantias fundamentais do HGR:

- O LLM **nunca perde contexto conversacional** após reinícios do servidor; a cache de chat é reconstruída integralmente a partir do SQLite na inicialização.
- Os factos do utilizador são **extraídos automaticamente** de cada troca usando padrões regex multilingues e são **sempre injetados** no system prompt no pedido seguinte.
- Um **threshold de relevância dinâmico** garante que o agente nunca inicie um pedido sem contexto, mesmo quando a similaridade léxica com steps anteriores é baixa.
- Um **scheduler cron asyncio nativo** está integrado diretamente no gestor de memória, sem dependências externas.

---

## Arquitetura Central

```
┌──────────────────────────────────────────────────────────┐
│                  MemoryEnhancedAgent                     │
│        (interface pública usada pelo agent_loop)         │
└─────────────────────────┬────────────────────────────────┘
                          │
             ┌────────────▼────────────┐
             │  HierarchicalMemory     │
             │       Manager           │
             └─┬──────┬──────┬─────┬──┘
               │      │      │     │
      ┌────────▼─┐ ┌───▼──┐ ┌▼──┐ ┌▼────────┐
      │  Chat    │ │Facts │ │Ctx│ │  Cron   │
      │ History  │ │ Mgr  │ │Stp│ │ Manager │
      │ Manager  │ │      │ │Mgr│ │         │
      └────────┬─┘ └───┬──┘ └┬──┘ └┬────────┘
               │       │     │     │
            ┌──▼───────▼─────▼─────▼──┐
            │        HGRDatabase       │
            │     (agent_memory.db)    │
            │   WAL · row_factory=Row  │
            └──────────────────────────┘
```

**Camadas de memória:**

| Camada | Armazenamento | TTL | Âmbito |
|---|---|---|---|
| Curto prazo | deque RAM | 1 hora | Steps de raciocínio recentes |
| Médio prazo | deque RAM | 24 horas | Contexto de sessão |
| Longo prazo | SQLite | Permanente | Factos, histórico de chat, cron jobs |

---

## Esquema do Banco de Dados

Todo o estado é guardado num **único ficheiro SQLite** (`agent_memory.db`) com quatro tabelas.

### `chat_log` — Histórico de conversa persistente

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | Auto-incremento |
| `user_id` | TEXT | Identificador do utilizador |
| `role` | TEXT | `user` ou `assistant` |
| `content` | TEXT | Corpo da mensagem |
| `timestamp` | REAL | Epoch Unix |
| `session_id` | TEXT | Hash MD5 diário |

Índice: `idx_chat_user_ts ON chat_log(user_id, timestamp DESC)`

---

### `facts` — Armazenamento chave-valor de conhecimento

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | Auto-incremento |
| `user_id` | TEXT | Identificador do utilizador |
| `key` | TEXT | Nome do facto (ÚNICO por utilizador) |
| `value` | TEXT | Valor do facto |
| `importance` | REAL | Peso de relevância 0.0–1.0 |
| `category` | TEXT | ex. `general`, `auto_extracted` |
| `tags` | TEXT | Array JSON |
| `access_count` | INTEGER | Contador de leituras |
| `last_accessed` | REAL | Epoch Unix |
| `created_at` | REAL | Epoch Unix |

---

### `context_steps` — Steps técnicos de raciocínio do agente

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | Auto-incremento |
| `user_id` | TEXT | Identificador do utilizador |
| `session_id` | TEXT | Hash da sessão |
| `query` | TEXT | Query original do utilizador |
| `thought` | TEXT | Raciocínio interno do agente |
| `action` | TEXT | Ação tomada (ex. `continue`, `tool_call`) |
| `confidence` | REAL | 0.0–1.0 |
| `importance` | REAL | 0.0–1.0 |
| `tool_used` | TEXT | Nome da ferramenta usada |
| `tool_result` | TEXT | Output truncado (máx. 300 caracteres) |
| `keywords` | TEXT | Tokens separados por espaço |
| `timestamp` | REAL | Epoch Unix |

---

### `cron_jobs` — Tarefas agendadas

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | Auto-incremento |
| `user_id` | TEXT | Dono do job |
| `name` | TEXT | Nome legível do job |
| `description` | TEXT | Descrição |
| `schedule` | TEXT | Cron 5 campos ou `every:Ns/Nm/Nh` |
| `task_type` | TEXT | `shell`, `agent`, etc. |
| `task` | TEXT | Comando ou instrução em linguagem natural |
| `status` | TEXT | `active`, `paused`, `done` |
| `last_run` | REAL | Epoch Unix |
| `next_run` | REAL | Epoch Unix |
| `run_count` | INTEGER | Total de execuções bem-sucedidas |
| `last_output` | TEXT | Resultado da última execução |
| `created_at` | REAL | Epoch Unix |

---

## Componentes

### `MemoryConfig`

Dataclass de configuração central. Todos os parâmetros têm valores predefinidos prontos para produção e podem ser alterados em tempo de execução via `PATCH /api/memory/config`.

```python
@dataclass
class MemoryConfig:
    db_path:              str   = "agent_memory.db"
    short_term_size:      int   = 30       # capacidade da deque RAM
    short_term_ttl:       int   = 3600     # 1 hora
    medium_term_size:     int   = 100      # capacidade da deque RAM
    medium_term_ttl:      int   = 86400    # 24 horas
    min_relevance_score:  float = 0.05     # piso do threshold dinâmico
    importance_threshold: float = 0.3      # mínimo para persistir steps no DB
    max_chat_history:     int   = 200      # máx. mensagens por utilizador no DB
    chat_history_to_llm:  int   = 40       # mensagens enviadas por pedido LLM
    max_facts_in_prompt:  int   = 20       # factos injetados no system prompt
    cron_tick_interval:   int   = 30       # intervalo de verificação do scheduler (s)
```

---

### `RelevanceScorer`

Classe utilitária sem estado. Calcula relevância de memória com sobreposição de keywords (similaridade Jaccard), decaimento temporal e boost de frequência de acesso.

| Método | Retorna | Descrição |
|---|---|---|
| `keywords(text)` | `set[str]` | Tokeniza texto, remove stop words (EN + PT) |
| `score(query, text, timestamp, access_count)` | `float` | Score de relevância 0.0–1.0 |
| `importance(thought, confidence, has_result)` | `float` | Calcula importância de um step |

---

### `HGRDatabase`

Wrapper SQLite de baixo nível. Todas as tabelas são criadas na primeira instanciação.

```python
db = HGRDatabase("agent_memory.db")
db.execute(sql, params)       # INSERT / UPDATE / DELETE
db.fetchone(sql, params)      # → sqlite3.Row | None
db.fetchall(sql, params)      # → List[sqlite3.Row]
```

Pragmas aplicados: `PRAGMA journal_mode=WAL` · `PRAGMA foreign_keys=ON`

---

### `ChatHistoryManager`

Gere o registo completo e persistente de conversas.

- Cada mensagem é escrita imediatamente no `chat_log`.
- A cache deque em RAM é populada de forma lazy a partir do SQLite após reinício.
- As linhas no DB por utilizador são limitadas a `max_chat_history`; as mensagens mais antigas são removidas automaticamente.

```python
chat.add(user_id, role, content)          # persiste + atualiza cache
chat.get(user_id, last_n=40)              # → List[{"role": str, "content": str}]
chat.clear(user_id)                       # → int (linhas eliminadas)
```

---

### `FactsManager`

Gere factos persistentes chave-valor sobre utilizadores, projetos e preferências.

**Padrões de extração automática (regex multilingue):**

| Padrão | Categoria | Importância |
|---|---|---|
| `me chamo` / `my name is` | `nome` | 0.95 |
| Endereço email | `email` | 0.90 |
| Linguagem preferida (Python, JS, etc.) | `linguagem_preferida` | 0.80 |
| Projeto ativo | `projeto_ativo` | 0.75 |
| Localização (`sou de` / `I live in`) | `localizacao` | 0.70 |
| Profissão (`sou` / `I'm a`) | `profissao` | 0.65 |

**Métodos principais:**

```python
facts.store(user_id, key, value,
            importance=0.5, category="general", tags=None)  # → bool (True=criado)
facts.get(user_id, key)                                      # → Fact | None
facts.get_all(user_id, min_importance=0.0)                   # → Dict[str, Fact]
facts.recall(user_id, category, limit, min_importance)       # → List[dict]
facts.delete(user_id, key, category, fact_id, delete_all)    # → int (eliminados)
facts.search(user_id, term)                                  # → List[dict]
facts.format_for_prompt(user_id)                             # → str (para system prompt)
facts.extract_from_exchange(user_id, user_msg, bot_reply)    # → List[str] (chaves)
facts.stats(user_id)                                         # → dict
```

---

### `ContextStepsManager`

Regista e recupera steps de raciocínio do agente para continuidade de contexto entre sessões.

- Steps com `importance >= importance_threshold` são persistidos no DB.
- Steps de menor importância ficam apenas na deque RAM de curto prazo.
- A recuperação usa um **threshold dinâmico**: se nenhum step ultrapassar `min_relevance_score`, o threshold é progressivamente reduzido até encontrar pelo menos um resultado. Fallback final: os 3 steps mais recentes no DB.

```python
steps.store(user_id, step: ContextStep)
steps.retrieve_relevant(user_id, query, max_items=5)  # → List[ContextStep]
steps.format_for_prompt(user_id, query)               # → str
```

---

### `CronManager`

Scheduler de tarefas nativo em `asyncio`. Sem dependências externas.

**Formatos de schedule suportados:**

| Formato | Exemplo | Significado |
|---|---|---|
| Intervalo (segundos) | `every:30s` | A cada 30 segundos |
| Intervalo (minutos) | `every:5m` | A cada 5 minutos |
| Intervalo (horas) | `every:2h` | A cada 2 horas |
| Cron standard | `0 8 * * *` | Diariamente às 08:00 |

```python
crons.create(user_id, name, description, schedule, task_type, task)  # → CronJob
crons.list_jobs(user_id, status=None)                                 # → List[CronJob]
crons.pause(job_id, user_id)
crons.resume(job_id, user_id)
crons.delete(job_id, user_id)
await crons.run_now(job_id, user_id)                                  # → dict
crons.set_executor(fn: Callable)                                      # injeta executor
await crons.start()                                                   # inicia scheduler
crons.format_next_run(job)                                            # → "em 5min" | "em 2h"
```

---

### `HierarchicalMemoryManager`

Orquestrador central. Mantém referências para todos os sub-gestores e produz o bloco de contexto final para o system prompt.

```python
mgr     = HierarchicalMemoryManager(config)
context = mgr.build_system_context(user_id, query)  # → str (não vazio se existirem dados)
session = mgr.session_id(user_id)                   # → hash MD5, renova diariamente
```

---

### `MemoryEnhancedAgent`

A **interface pública** entre o `agent_loop` de `openbot.py` e todo o subsistema HGR. Mantém compatibilidade total com a v3.1.

```python
agent = MemoryEnhancedAgent(config=None)

# Acessores de propriedades
agent.db      # → HGRDatabase
agent.facts   # → FactsManager
agent.crons   # → CronManager

# Chat
agent.add_chat_message(user_id, role, content)
agent.get_chat_history(user_id, last_n=40)   # → List[dict]
agent.clear_chat_history(user_id)            # → int

# System prompt
agent.get_enhanced_system_prompt(user_id, query, base_prompt)  # → str

# Factos
agent.store_fact(user_id, key, value, importance, category, tags)
agent.get_user_facts(user_id)                        # → Dict[str, Fact]
agent.extract_and_store_facts(user_id, msg, reply)   # → List[str]

# Steps de raciocínio
agent.record_step(user_id, query, step_data)

# Estatísticas
agent.get_stats(user_id)   # → dict

# Cron
agent.set_cron_executor(fn)
await agent.start_cron_scheduler()
```

---

## Referência da API Pública

### `get_enhanced_system_prompt(user_id, query, base_prompt) → str`

Enriquece o system prompt base com dois blocos:

1. **Bloco de factos** — todos os factos conhecidos sobre o utilizador, formatados como pares chave-valor.
2. **Bloco de steps** — os steps de raciocínio anteriores mais relevantes, com timestamps e scores de confiança.

Ambos os blocos são adicionados se existirem dados. O agente **nunca** inicia um pedido sem contexto.

---

### `extract_and_store_facts(user_id, user_msg, bot_reply) → List[str]`

Deve ser chamado após **cada resposta final do LLM**. Executa regex multilingue sobre ambas as mensagens e persiste os factos descobertos. Devolve a lista de chaves de factos criados ou atualizados.

---

### `record_step(user_id, query, step_data) → None`

Regista um step de raciocínio do agente. O dict `step_data` aceita:

```python
{
    "thought":     str,    # monólogo interno
    "action":      str,    # "continue", "tool_call", "final_answer"
    "confidence":  float,  # 0.0–1.0
    "tool":        str,    # nome da ferramenta invocada
    "result":      str,    # output da ferramenta
    "code_result": str,    # output de execução de código
}
```

---

## Parâmetros de Configuração

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `db_path` | `agent_memory.db` | Caminho do ficheiro SQLite |
| `short_term_size` | `30` | Capacidade da deque RAM de curto prazo |
| `short_term_ttl` | `3600` | TTL de curto prazo (segundos) |
| `medium_term_size` | `100` | Capacidade da deque RAM de médio prazo |
| `medium_term_ttl` | `86400` | TTL de médio prazo (segundos) |
| `min_relevance_score` | `0.05` | Piso do threshold dinâmico para recuperação de contexto |
| `importance_threshold` | `0.3` | Importância mínima para persistir step no DB |
| `max_chat_history` | `200` | Máx. mensagens armazenadas por utilizador |
| `chat_history_to_llm` | `40` | Mensagens enviadas por pedido LLM |
| `max_facts_in_prompt` | `20` | Máx. factos injetados por system prompt |
| `cron_tick_interval` | `30` | Intervalo de tick do scheduler (segundos) |

---

## Fluxo de Dados

```
Mensagem do utilizador chega
        │
        ▼
get_enhanced_system_prompt(user_id, query, base_prompt)
  ├── facts.format_for_prompt(user_id)         → injetar factos do utilizador
  └── steps.format_for_prompt(user_id, query)  → injetar steps anteriores relevantes
        │
        ▼
agent_loop() → chamada ao LLM
  (system prompt enriquecido + últimas N mensagens de chat)
        │
        ▼
record_step(user_id, query, step_data)          → guardar step de raciocínio
        │
        ▼
Resposta final devolvida ao utilizador
        │
        ▼
add_chat_message(user_id, "user", user_msg)
add_chat_message(user_id, "assistant", response) → persistir ambas as mensagens
        │
        ▼
extract_and_store_facts(user_id, user_msg, response) → extrair novos factos
```

---

## Integração com o OPENBOT

O HGR é importado na inicialização e é criada uma instância global:

```python
from HGR import MemoryEnhancedAgent, MemoryConfig

memory_agent = MemoryEnhancedAgent()
```

A instância é usada por todo o `openbot.py`:

```python
# Antes de cada chamada ao LLM
system_prompt = memory_agent.get_enhanced_system_prompt(uid, query, BASE_PROMPT)

# Após cada resposta final
memory_agent.add_chat_message(uid, "user", user_msg)
memory_agent.add_chat_message(uid, "assistant", response)
memory_agent.extract_and_store_facts(uid, user_msg, response)
memory_agent.record_step(uid, query, step_data)
```

O executor cron é registado na inicialização:

```python
async def _hgr_cron_executor(job) -> str:
    # executa comandos shell ou tarefas de agente
    ...

memory_agent.set_cron_executor(_hgr_cron_executor)
await memory_agent.start_cron_scheduler()
```

---

## Endpoints REST

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/memory/list` | Listar factos (`?category`, `?search`, `?limit`, `?min_importance`) |
| `GET` | `/api/memory/context-steps` | Listar steps de raciocínio (`?limit`) |
| `GET` | `/api/memory/stats` | Estatísticas de memória |
| `PATCH` | `/api/memory/config` | Atualizar MemoryConfig em tempo de execução |
| `DELETE` | `/api/memory/clear` | Limpar histórico de chat |
| `GET` | `/api/crons/list` | Listar cron jobs (`?status`) |
| `POST` | `/api/crons/create` | Criar um novo cron job |
| `POST` | `/api/crons/run-now` | Executar um job imediatamente |
| `PATCH` | `/api/crons/pause` | Pausar um job |
| `PATCH` | `/api/crons/resume` | Retomar um job |
| `DELETE` | `/api/crons/delete` | Eliminar um job |

Todos os endpoints requerem autenticação JWT Bearer via `require_auth()`.

---

## Extração Automática de Factos

Os factos são extraídos proativamente de cada troca de conversa usando padrões regex multilingues compilados.

**Exemplo:**

```
Utilizador: "O meu nome é Ana e trabalho com TypeScript"
Bot:        "Olá Ana! TypeScript é uma excelente escolha."
```

Factos criados:
- `nome` → `"Ana"` (importância: 0.95, categoria: `auto_extracted`)
- `linguagem_preferida` → `"TypeScript"` (importância: 0.80, categoria: `auto_extracted`)

Estes factos estão disponíveis no system prompt do pedido seguinte de imediato.

---

## Agendamento Cron

```python
# Cron standard (08:00 todos os dias)
job = agent.crons.create(
    uid, "Resumo Diário", "Sumário matinal",
    "0 8 * * *", "agent", "Resume a agenda de hoje"
)

# Atalho de intervalo (a cada 5 minutos)
job = agent.crons.create(
    uid, "Heartbeat", "Verificação do sistema",
    "every:5m", "shell", "echo alive"
)

print(agent.crons.format_next_run(job))   # "em 4min"
```

---

## Início Rápido

```python
from HGR import MemoryEnhancedAgent

agent = MemoryEnhancedAgent()
uid   = "utilizador_001"

# 1. Guardar um facto manualmente
agent.store_fact(uid, "linguagem_preferida", "Python", importance=0.8)

# 2. Registar uma troca de conversa
agent.add_chat_message(uid, "user",      "Olá, estou a construir um serviço FastAPI")
agent.add_chat_message(uid, "assistant", "Ótimo! FastAPI é excelente para APIs REST.")

# 3. Extrair factos automaticamente da troca
keys = agent.extract_and_store_facts(
    uid,
    "Olá, estou a construir um serviço FastAPI",
    "Ótimo! FastAPI é excelente para APIs REST."
)
print(keys)   # ["projeto_ativo"]

# 4. Enriquecer o próximo system prompt
prompt = agent.get_enhanced_system_prompt(uid, "ajuda com rotas", "Tu és o OPENBOT.")
print(prompt)   # base prompt + bloco de factos + bloco de steps

# 5. Verificar estatísticas
print(agent.get_stats(uid))
```

---

## Melhorias em relação à v3.1

| Funcionalidade | v3.1 | v4.0 |
|---|---|---|
| Persistência do histórico de chat | Só RAM — perdido ao reiniciar | SQLite — sobrevive a reinícios |
| Armazenamento de factos | Classe `MemorySQL` separada | Tabela `facts` unificada em `agent_memory.db` |
| Injeção de contexto | Opcional | Sempre obrigatória |
| Extração de factos | Apenas manual | Automática após cada troca |
| Threshold de relevância | Estático | Dinâmico — nunca devolve contexto vazio |
| Scheduler cron | Biblioteca externa | `asyncio` nativo no HGR |
| Ficheiros de base de dados | Múltiplos DBs separados | Único `agent_memory.db` |
| Boost temporal | Não | Sim — memórias recentes têm prioridade |
| Boost de frequência | Não | Sim — factos acedidos frequentemente têm prioridade |

---

```
agent_memory.db
├── chat_log         ← histórico completo de conversas (persistente entre reinícios)
│     └── cache RAM reconstruída na inicialização
├── facts            ← armazém chave-valor de utilizador/projeto
│     ├── extraído automaticamente após cada troca
│     └── injetado em cada system prompt
├── context_steps    ← steps de raciocínio do agente
│     ├── persistidos se importância ≥ 0.3
│     └── recuperados por scoring de relevância dinâmica
└── cron_jobs        ← tarefas agendadas
      ├── scheduler asyncio, tick a cada 30s
      └── executor registado a partir do openbot.py
```

---

*Fonte: `HGR.py` — OPENBOT v4.0 · Março 2026 · Idioma: Português*
