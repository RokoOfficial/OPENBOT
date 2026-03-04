# HGR v4.0 — Hierarchical Grounded Reasoning
## Sistema de Memoria Persistente para Agentes Cognitivos · OPENBOT

> **Versión:** 4.0 · **Licencia:** Open-Source · **Runtime:** Python 3.10+ · **Base de datos:** SQLite (WAL)

---

## Índice

1. [Visión General](#visión-general)
2. [Arquitectura Central](#arquitectura-central)
3. [Esquema de Base de Datos](#esquema-de-base-de-datos)
4. [Componentes](#componentes)
5. [Referencia de la API Pública](#referencia-de-la-api-pública)
6. [Parámetros de Configuración](#parámetros-de-configuración)
7. [Flujo de Datos](#flujo-de-datos)
8. [Integración con OPENBOT](#integración-con-openbot)
9. [Endpoints REST](#endpoints-rest)
10. [Extracción Automática de Hechos](#extracción-automática-de-hechos)
11. [Planificación Cron](#planificación-cron)
12. [Inicio Rápido](#inicio-rápido)
13. [Mejoras respecto a v3.1](#mejoras-respecto-a-v31)

---

## Visión General

**HGR** (Hierarchical Grounded Reasoning) es el subsistema de memoria persistente de OPENBOT v4.0. Equipa al agente con tres capas de memoria complementarias — una caché RAM a corto plazo, un almacenamiento de sesión en memoria y una capa de persistencia SQLite a largo plazo — todas orquestadas a través de un único archivo de base de datos unificado (`agent_memory.db`).

Garantías fundamentales de HGR:

- El LLM **nunca pierde el contexto conversacional** tras reinicios del servidor; la caché de chat se reconstruye completamente desde SQLite en el arranque.
- Los hechos del usuario se **extraen automáticamente** de cada intercambio usando patrones regex multilingües y se **inyectan siempre** en el system prompt en la siguiente solicitud.
- Un **umbral de relevancia dinámico** garantiza que el agente nunca inicie una solicitud sin contexto, incluso cuando la similitud léxica con pasos anteriores es baja.
- Un **planificador cron asyncio nativo** está integrado directamente en el gestor de memoria, sin dependencias externas.

---

## Arquitectura Central

```
┌──────────────────────────────────────────────────────────┐
│                  MemoryEnhancedAgent                     │
│         (interfaz pública usada por agent_loop)          │
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

**Capas de memoria:**

| Capa | Almacenamiento | TTL | Ámbito |
|---|---|---|---|
| Corto plazo | deque RAM | 1 hora | Pasos de razonamiento recientes |
| Medio plazo | deque RAM | 24 horas | Contexto de sesión |
| Largo plazo | SQLite | Permanente | Hechos, historial de chat, cron jobs |

---

## Esquema de Base de Datos

Todo el estado se guarda en un **único archivo SQLite** (`agent_memory.db`) con cuatro tablas.

### `chat_log` — Historial de conversación persistente

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | INTEGER PK | Auto-incremento |
| `user_id` | TEXT | Identificador del usuario |
| `role` | TEXT | `user` o `assistant` |
| `content` | TEXT | Cuerpo del mensaje |
| `timestamp` | REAL | Epoch Unix |
| `session_id` | TEXT | Hash MD5 diario |

Índice: `idx_chat_user_ts ON chat_log(user_id, timestamp DESC)`

---

### `facts` — Almacén clave-valor de conocimiento

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | INTEGER PK | Auto-incremento |
| `user_id` | TEXT | Identificador del usuario |
| `key` | TEXT | Nombre del hecho (ÚNICO por usuario) |
| `value` | TEXT | Valor del hecho |
| `importance` | REAL | Peso de relevancia 0.0–1.0 |
| `category` | TEXT | p.ej. `general`, `auto_extracted` |
| `tags` | TEXT | Array JSON |
| `access_count` | INTEGER | Contador de lecturas |
| `last_accessed` | REAL | Epoch Unix |
| `created_at` | REAL | Epoch Unix |

---

### `context_steps` — Pasos técnicos de razonamiento del agente

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | INTEGER PK | Auto-incremento |
| `user_id` | TEXT | Identificador del usuario |
| `session_id` | TEXT | Hash de sesión |
| `query` | TEXT | Consulta original del usuario |
| `thought` | TEXT | Razonamiento interno del agente |
| `action` | TEXT | Acción tomada (p.ej. `continue`, `tool_call`) |
| `confidence` | REAL | 0.0–1.0 |
| `importance` | REAL | 0.0–1.0 |
| `tool_used` | TEXT | Nombre de la herramienta utilizada |
| `tool_result` | TEXT | Salida truncada (máx. 300 caracteres) |
| `keywords` | TEXT | Tokens separados por espacios |
| `timestamp` | REAL | Epoch Unix |

---

### `cron_jobs` — Tareas programadas

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | INTEGER PK | Auto-incremento |
| `user_id` | TEXT | Propietario del job |
| `name` | TEXT | Nombre legible del job |
| `description` | TEXT | Descripción |
| `schedule` | TEXT | Cron 5 campos o `every:Ns/Nm/Nh` |
| `task_type` | TEXT | `shell`, `agent`, etc. |
| `task` | TEXT | Comando o instrucción en lenguaje natural |
| `status` | TEXT | `active`, `paused`, `done` |
| `last_run` | REAL | Epoch Unix |
| `next_run` | REAL | Epoch Unix |
| `run_count` | INTEGER | Total de ejecuciones exitosas |
| `last_output` | TEXT | Resultado de la última ejecución |
| `created_at` | REAL | Epoch Unix |

---

## Componentes

### `MemoryConfig`

Dataclass de configuración central. Todos los parámetros tienen valores predeterminados listos para producción y pueden modificarse en tiempo de ejecución vía `PATCH /api/memory/config`.

```python
@dataclass
class MemoryConfig:
    db_path:              str   = "agent_memory.db"
    short_term_size:      int   = 30       # capacidad del deque RAM
    short_term_ttl:       int   = 3600     # 1 hora
    medium_term_size:     int   = 100      # capacidad del deque RAM
    medium_term_ttl:      int   = 86400    # 24 horas
    min_relevance_score:  float = 0.05     # piso del umbral dinámico
    importance_threshold: float = 0.3      # mínimo para persistir pasos en DB
    max_chat_history:     int   = 200      # máx. mensajes por usuario en DB
    chat_history_to_llm:  int   = 40       # mensajes enviados por solicitud LLM
    max_facts_in_prompt:  int   = 20       # hechos inyectados en el system prompt
    cron_tick_interval:   int   = 30       # intervalo de verificación del scheduler (s)
```

---

### `RelevanceScorer`

Clase utilitaria sin estado. Calcula relevancia de memoria mediante solapamiento de palabras clave (similitud Jaccard), decaimiento temporal y boost de frecuencia de acceso.

| Método | Retorna | Descripción |
|---|---|---|
| `keywords(text)` | `set[str]` | Tokeniza texto, elimina stop words (EN + PT) |
| `score(query, text, timestamp, access_count)` | `float` | Puntuación de relevancia 0.0–1.0 |
| `importance(thought, confidence, has_result)` | `float` | Calcula importancia de un paso |

---

### `HGRDatabase`

Wrapper SQLite de bajo nivel. Todas las tablas se crean en la primera instanciación.

```python
db = HGRDatabase("agent_memory.db")
db.execute(sql, params)       # INSERT / UPDATE / DELETE
db.fetchone(sql, params)      # → sqlite3.Row | None
db.fetchall(sql, params)      # → List[sqlite3.Row]
```

Pragmas aplicados: `PRAGMA journal_mode=WAL` · `PRAGMA foreign_keys=ON`

---

### `ChatHistoryManager`

Gestiona el registro completo y persistente de conversaciones.

- Cada mensaje se escribe inmediatamente en `chat_log`.
- La caché deque en RAM se popula de forma lazy desde SQLite tras un reinicio.
- Las filas en DB por usuario se limitan a `max_chat_history`; los mensajes más antiguos se eliminan automáticamente.

```python
chat.add(user_id, role, content)          # persiste + actualiza caché
chat.get(user_id, last_n=40)              # → List[{"role": str, "content": str}]
chat.clear(user_id)                       # → int (filas eliminadas)
```

---

### `FactsManager`

Gestiona hechos persistentes clave-valor sobre usuarios, proyectos y preferencias.

**Patrones de extracción automática (regex multilingüe):**

| Patrón | Categoría | Importancia |
|---|---|---|
| `me chamo` / `my name is` | `nome` | 0.95 |
| Dirección email | `email` | 0.90 |
| Lenguaje preferido (Python, JS, etc.) | `linguagem_preferida` | 0.80 |
| Proyecto activo | `projeto_ativo` | 0.75 |
| Ubicación (`sou de` / `I live in`) | `localizacao` | 0.70 |
| Profesión (`sou` / `I'm a`) | `profissao` | 0.65 |

**Métodos principales:**

```python
facts.store(user_id, key, value,
            importance=0.5, category="general", tags=None)  # → bool (True=creado)
facts.get(user_id, key)                                      # → Fact | None
facts.get_all(user_id, min_importance=0.0)                   # → Dict[str, Fact]
facts.recall(user_id, category, limit, min_importance)       # → List[dict]
facts.delete(user_id, key, category, fact_id, delete_all)    # → int (eliminados)
facts.search(user_id, term)                                  # → List[dict]
facts.format_for_prompt(user_id)                             # → str (para system prompt)
facts.extract_from_exchange(user_id, user_msg, bot_reply)    # → List[str] (claves)
facts.stats(user_id)                                         # → dict
```

---

### `ContextStepsManager`

Registra y recupera pasos de razonamiento del agente para continuidad de contexto entre sesiones.

- Los pasos con `importance >= importance_threshold` se persisten en DB.
- Los pasos de menor importancia permanecen solo en el deque RAM a corto plazo.
- La recuperación usa un **umbral dinámico**: si ningún paso supera `min_relevance_score`, el umbral se reduce progresivamente hasta encontrar al menos un resultado. Fallback final: los 3 pasos más recientes en DB.

```python
steps.store(user_id, step: ContextStep)
steps.retrieve_relevant(user_id, query, max_items=5)  # → List[ContextStep]
steps.format_for_prompt(user_id, query)               # → str
```

---

### `CronManager`

Planificador de tareas nativo en `asyncio`. Sin dependencias externas.

**Formatos de schedule soportados:**

| Formato | Ejemplo | Significado |
|---|---|---|
| Intervalo (segundos) | `every:30s` | Cada 30 segundos |
| Intervalo (minutos) | `every:5m` | Cada 5 minutos |
| Intervalo (horas) | `every:2h` | Cada 2 horas |
| Cron estándar | `0 8 * * *` | Diariamente a las 08:00 |

```python
crons.create(user_id, name, description, schedule, task_type, task)  # → CronJob
crons.list_jobs(user_id, status=None)                                 # → List[CronJob]
crons.pause(job_id, user_id)
crons.resume(job_id, user_id)
crons.delete(job_id, user_id)
await crons.run_now(job_id, user_id)                                  # → dict
crons.set_executor(fn: Callable)                                      # inyectar executor
await crons.start()                                                   # iniciar scheduler
crons.format_next_run(job)                                            # → "en 5min" | "en 2h"
```

---

### `HierarchicalMemoryManager`

Orquestador central. Mantiene referencias a todos los sub-gestores y produce el bloque de contexto final para el system prompt.

```python
mgr     = HierarchicalMemoryManager(config)
context = mgr.build_system_context(user_id, query)  # → str (no vacío si hay datos)
session = mgr.session_id(user_id)                   # → hash MD5, se renueva diariamente
```

---

### `MemoryEnhancedAgent`

La **interfaz pública** entre el `agent_loop` de `openbot.py` y todo el subsistema HGR. Mantiene compatibilidad total con v3.1.

```python
agent = MemoryEnhancedAgent(config=None)

# Accesores de propiedades
agent.db      # → HGRDatabase
agent.facts   # → FactsManager
agent.crons   # → CronManager

# Chat
agent.add_chat_message(user_id, role, content)
agent.get_chat_history(user_id, last_n=40)   # → List[dict]
agent.clear_chat_history(user_id)            # → int

# System prompt
agent.get_enhanced_system_prompt(user_id, query, base_prompt)  # → str

# Hechos
agent.store_fact(user_id, key, value, importance, category, tags)
agent.get_user_facts(user_id)                        # → Dict[str, Fact]
agent.extract_and_store_facts(user_id, msg, reply)   # → List[str]

# Pasos de razonamiento
agent.record_step(user_id, query, step_data)

# Estadísticas
agent.get_stats(user_id)   # → dict

# Cron
agent.set_cron_executor(fn)
await agent.start_cron_scheduler()
```

---

## Referencia de la API Pública

### `get_enhanced_system_prompt(user_id, query, base_prompt) → str`

Enriquece el system prompt base con dos bloques:

1. **Bloque de hechos** — todos los hechos conocidos sobre el usuario, formateados como pares clave-valor.
2. **Bloque de pasos** — los pasos de razonamiento anteriores más relevantes, con timestamps y puntuaciones de confianza.

Ambos bloques se añaden si existen datos. El agente **nunca** inicia una solicitud sin contexto.

---

### `extract_and_store_facts(user_id, user_msg, bot_reply) → List[str]`

Debe llamarse tras **cada respuesta final del LLM**. Ejecuta regex multilingüe sobre ambos turnos y persiste los hechos descubiertos. Devuelve la lista de claves de hechos creados o actualizados.

---

### `record_step(user_id, query, step_data) → None`

Registra un paso de razonamiento del agente. El dict `step_data` acepta:

```python
{
    "thought":     str,    # monólogo interno
    "action":      str,    # "continue", "tool_call", "final_answer"
    "confidence":  float,  # 0.0–1.0
    "tool":        str,    # nombre de la herramienta invocada
    "result":      str,    # salida de la herramienta
    "code_result": str,    # salida de ejecución de código
}
```

---

## Parámetros de Configuración

| Parámetro | Predeterminado | Descripción |
|---|---|---|
| `db_path` | `agent_memory.db` | Ruta del archivo SQLite |
| `short_term_size` | `30` | Capacidad del deque RAM a corto plazo |
| `short_term_ttl` | `3600` | TTL a corto plazo (segundos) |
| `medium_term_size` | `100` | Capacidad del deque RAM a medio plazo |
| `medium_term_ttl` | `86400` | TTL a medio plazo (segundos) |
| `min_relevance_score` | `0.05` | Piso del umbral dinámico para recuperación |
| `importance_threshold` | `0.3` | Importancia mínima para persistir pasos en DB |
| `max_chat_history` | `200` | Máx. mensajes almacenados por usuario |
| `chat_history_to_llm` | `40` | Mensajes enviados por solicitud LLM |
| `max_facts_in_prompt` | `20` | Máx. hechos inyectados por system prompt |
| `cron_tick_interval` | `30` | Intervalo de tick del scheduler (segundos) |

---

## Flujo de Datos

```
Mensaje del usuario llega
        │
        ▼
get_enhanced_system_prompt(user_id, query, base_prompt)
  ├── facts.format_for_prompt(user_id)         → inyectar hechos del usuario
  └── steps.format_for_prompt(user_id, query)  → inyectar pasos anteriores relevantes
        │
        ▼
agent_loop() → llamada al LLM
  (system prompt enriquecido + últimos N mensajes de chat)
        │
        ▼
record_step(user_id, query, step_data)          → guardar paso de razonamiento
        │
        ▼
Respuesta final devuelta al usuario
        │
        ▼
add_chat_message(user_id, "user", user_msg)
add_chat_message(user_id, "assistant", response) → persistir ambos turnos
        │
        ▼
extract_and_store_facts(user_id, user_msg, response) → extraer nuevos hechos
```

---

## Integración con OPENBOT

HGR se importa en el arranque y se crea una instancia global:

```python
from HGR import MemoryEnhancedAgent, MemoryConfig

memory_agent = MemoryEnhancedAgent()
```

La instancia se usa en todo `openbot.py`:

```python
# Antes de cada llamada al LLM
system_prompt = memory_agent.get_enhanced_system_prompt(uid, query, BASE_PROMPT)

# Tras cada respuesta final
memory_agent.add_chat_message(uid, "user", user_msg)
memory_agent.add_chat_message(uid, "assistant", response)
memory_agent.extract_and_store_facts(uid, user_msg, response)
memory_agent.record_step(uid, query, step_data)
```

El executor cron se registra en el arranque:

```python
async def _hgr_cron_executor(job) -> str:
    # ejecuta comandos shell o tareas de agente
    ...

memory_agent.set_cron_executor(_hgr_cron_executor)
await memory_agent.start_cron_scheduler()
```

---

## Endpoints REST

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/api/memory/list` | Listar hechos (`?category`, `?search`, `?limit`, `?min_importance`) |
| `GET` | `/api/memory/context-steps` | Listar pasos de razonamiento (`?limit`) |
| `GET` | `/api/memory/stats` | Estadísticas de memoria |
| `PATCH` | `/api/memory/config` | Actualizar MemoryConfig en tiempo de ejecución |
| `DELETE` | `/api/memory/clear` | Limpiar historial de chat |
| `GET` | `/api/crons/list` | Listar cron jobs (`?status`) |
| `POST` | `/api/crons/create` | Crear un nuevo cron job |
| `POST` | `/api/crons/run-now` | Ejecutar un job inmediatamente |
| `PATCH` | `/api/crons/pause` | Pausar un job |
| `PATCH` | `/api/crons/resume` | Reanudar un job |
| `DELETE` | `/api/crons/delete` | Eliminar un job |

Todos los endpoints requieren autenticación JWT Bearer vía `require_auth()`.

---

## Extracción Automática de Hechos

Los hechos se extraen proactivamente de cada intercambio de conversación usando patrones regex multilingües compilados.

**Ejemplo:**

```
Usuario: "Mi nombre es Ana y trabajo con TypeScript"
Bot:     "¡Hola Ana! TypeScript es una excelente elección."
```

Hechos creados:
- `nome` → `"Ana"` (importancia: 0.95, categoría: `auto_extracted`)
- `linguagem_preferida` → `"TypeScript"` (importancia: 0.80, categoría: `auto_extracted`)

Estos hechos están disponibles en el system prompt de la siguiente solicitud de inmediato.

---

## Planificación Cron

```python
# Cron estándar (08:00 todos los días)
job = agent.crons.create(
    uid, "Resumen Diario", "Resumen matutino",
    "0 8 * * *", "agent", "Resume la agenda de hoy"
)

# Atajo de intervalo (cada 5 minutos)
job = agent.crons.create(
    uid, "Heartbeat", "Verificación del sistema",
    "every:5m", "shell", "echo alive"
)

print(agent.crons.format_next_run(job))   # "en 4min"
```

---

## Inicio Rápido

```python
from HGR import MemoryEnhancedAgent

agent = MemoryEnhancedAgent()
uid   = "usuario_001"

# 1. Guardar un hecho manualmente
agent.store_fact(uid, "lenguaje_preferido", "Python", importance=0.8)

# 2. Registrar un turno de conversación
agent.add_chat_message(uid, "user",      "Hola, estoy construyendo un servicio FastAPI")
agent.add_chat_message(uid, "assistant", "¡Excelente! FastAPI es ideal para APIs REST.")

# 3. Extraer hechos automáticamente del intercambio
keys = agent.extract_and_store_facts(
    uid,
    "Hola, estoy construyendo un servicio FastAPI",
    "¡Excelente! FastAPI es ideal para APIs REST."
)
print(keys)   # ["projeto_ativo"]

# 4. Enriquecer el siguiente system prompt
prompt = agent.get_enhanced_system_prompt(uid, "ayuda con rutas", "Eres OPENBOT.")
print(prompt)   # prompt base + bloque de hechos + bloque de pasos

# 5. Verificar estadísticas
print(agent.get_stats(uid))
```

---

## Mejoras respecto a v3.1

| Funcionalidad | v3.1 | v4.0 |
|---|---|---|
| Persistencia del historial de chat | Solo RAM — perdido al reiniciar | SQLite — sobrevive a reinicios |
| Almacenamiento de hechos | Clase `MemorySQL` separada | Tabla `facts` unificada en `agent_memory.db` |
| Inyección de contexto | Opcional | Siempre obligatoria |
| Extracción de hechos | Solo manual | Automática tras cada intercambio |
| Umbral de relevancia | Estático | Dinámico — nunca devuelve contexto vacío |
| Planificador cron | Biblioteca externa | `asyncio` nativo en HGR |
| Archivos de base de datos | Múltiples DBs separados | Único `agent_memory.db` |
| Boost temporal | No | Sí — memorias recientes tienen prioridad |
| Boost de frecuencia | No | Sí — hechos accedidos frecuentemente tienen prioridad |

---

```
agent_memory.db
├── chat_log         ← historial completo de conversaciones (persistente entre reinicios)
│     └── caché RAM reconstruida en el arranque
├── facts            ← almacén clave-valor de usuario/proyecto
│     ├── extraído automáticamente tras cada intercambio
│     └── inyectado en cada system prompt
├── context_steps    ← pasos de razonamiento del agente
│     ├── persistidos si importancia ≥ 0.3
│     └── recuperados por scoring de relevancia dinámica
└── cron_jobs        ← tareas programadas
      ├── scheduler asyncio, tick cada 30s
      └── executor registrado desde openbot.py
```

---

*Fuente: `HGR.py` — OPENBOT v4.0 · Marzo 2026 · Idioma: Español*
