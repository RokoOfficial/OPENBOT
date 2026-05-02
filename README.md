<p align="center">
  <img src="assets/logo.png" alt="OPENBOT Logo" width="320">
</p>

# OPENBOT 5.1

Backend assíncrono em Python para agente com autenticação JWT, memória HGR persistente, múltiplos provedores LLM e **integração HVM/HMP distribuída via HTTP**.

> **Versão 5.1:** adiciona serviço dedicado `BOT/hvm_api.py` (porta `7777`) e categoria de ferramentas `HVM` no core (`BOT/openbot.py`) para executar HMP/HVM por API remota.

---

## Visão geral

O OPENBOT 5.1 combina cinco blocos principais:

1. **API assíncrona principal** com Quart/Hypercorn (`BOT/openbot.py`).
2. **Memória HGR** persistente com SQLite.
3. **Autenticação** com JWT + bcrypt.
4. **Camada de tools** com múltiplas categorias, incluindo `HVM`.
5. **HVM API dedicada** para execução distribuída de HMP/HVM (`BOT/hvm_api.py`).

### Stack atual

- Python 3.8+
- Quart + Hypercorn
- SQLite
- JWT / bcrypt
- `openai==0.28.1` com compat layer para OpenAI, DeepSeek e Groq
- `aiohttp` para integração HTTP da categoria HVM
- Tailwind via CDN no frontend

---

## Estrutura do projeto

```text
OPENBOT/
├── assets/
│   └── logo.png
├── BOT/
│   ├── openbot.py          # servidor principal + ferramentas (inclui tools HVM via HTTP)
│   ├── hvm_api.py          # NOVO: API HVM/HMP dedicada (porta 7777)
│   ├── openbot_cors.py     # entrypoint com CORS
│   ├── openbot_shared.py   # configuração compartilhada/providers
│   ├── HGR.py              # memória persistente e cron jobs
│   ├── auth_system.py      # autenticação JWT + bcrypt
│   ├── config.py           # config tipada para ambientes
│   ├── install.sh          # instalação guiada
│   └── README.md
├── WEB/
│   └── index.html
├── docs/
│   ├── HGR_PT.md
│   ├── HGR_EN.md
│   ├── HGR_ES.md
│   └── REFATORACAO.md
├── LICENSE
└── README.md
```

---

## Início rápido

### 1) Instalação

```bash
bash BOT/install.sh
```

### 2) Subir OPENBOT principal

```bash
python BOT/openbot.py
```

### 3) Subir OPENBOT com CORS

```bash
python BOT/openbot_cors.py
```

### 4) Subir HVM API dedicada (porta 7777)

```bash
python BOT/hvm_api.py
```

### 5) Conectar OPENBOT à HVM API

```bash
export HVM_API_BASE="http://127.0.0.1:7777"
export HVM_API_TOKEN="hvm_token_aqui"
```

---

## Fluxo HVM/HMP distribuído (5.1)

1. Cliente chama tool HVM no OPENBOT (ex.: `hvm_run_code`).
2. `openbot.py` encaminha via HTTP para `hvm_api.py`.
3. `hvm_api.py` valida token/escopo e executa `Engine.run_code(...)`.
4. Resultado com `vars`, `logs`, `metrics` e `result` retorna ao OPENBOT.

Tools HVM já registradas no OPENBOT:
- `hvm_run_code`
- `hvm_status`
- `hvm_tools_list`
- `hvm_fs_list`

---

## Variáveis de ambiente

| Variável | Descrição | Padrão |
|---|---|---|
| `OPENBOT_PROVIDER` | Provider ativo (`deepseek`, `groq`, `openai`) | `deepseek` |
| `OPENBOT_MODEL` | Modelo LLM | default do provider |
| `DEEPSEEK_API_KEY` | Chave DeepSeek | — |
| `GROQ_API_KEY` | Chave Groq | — |
| `OPENAI_API_KEY` | Chave OpenAI | — |
| `JWT_SECRET` | Segredo JWT da API principal | obrigatório em produção |
| `OPENBOT_ENV` | `development`, `testing`, `production` | `development` |
| `OPENBOT_BASE_DIR` | diretório de trabalho do agente | `~/openbot_workspace` |
| `HOST` | host HTTP (app atual em execução) | `0.0.0.0` |
| `PORT` | porta HTTP (app atual em execução) | `5000` (OPENBOT) / `7777` (HVM API) |
| `CORS_ORIGINS` | `*` ou lista separada por vírgula | `*` |
| `HVM_API_BASE` | URL base da HVM API consumida pelo OPENBOT | `http://127.0.0.1:7777` |
| `HVM_API_TOKEN` | Bearer token usado nas tools HVM | vazio |
| `DB_PATH` | SQLite da HVM API | `hvm_auth.sqlite3` |
| `FS_ROOT` | raiz de filesystem permitida na HVM API | `~/openbot_workspace` |

---

## Endpoints principais

### OPENBOT (porta 5000)

Públicos:
- `POST /api/auth/register`
- `POST /api/auth/login`

Protegidos:
- `POST /api/auth/logout`
- `POST /api/chat`
- `POST /api/chat/stream`
- `POST /api/chat/clear`
- `GET /api/provider/list`
- `POST /api/provider/switch`
- `GET /api/tools/list`
- `POST /api/tools/execute/<name>`
- `GET /api/tools/history`
- `GET /api/user/profile`
- `GET /api/memory/stats`
- `GET /api/crons/list`

### HVM API (porta 7777)

Auth:
- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`
- `POST /auth/logout`

Execução HVM/HMP:
- `POST /hvm/run/code`
- `POST /hvm/run/batch`
- `GET /hvm/status`
- `GET /hvm/last`

Tools/FS:
- `GET /hvm/tools`
- `DELETE /hvm/tools/<name>`
- `GET /fs/list`
- `POST /fs/mkdir`

---

## Segurança

- **Nunca** versione segredos reais (tokens/chaves) em arquivos ou commits.
- Use `JWT_SECRET` forte em produção.
- Restrinja `CORS_ORIGINS` para seus domínios.
- Na HVM API, use token com escopo mínimo (`run` e/ou `tools`).
- Mantenha `FS_ROOT` restrito ao workspace necessário.
- Rotacione imediatamente qualquer credencial exposta.

---

## Limitações conhecidas

- `BOT/openbot.py` ainda é monolítico e concentra muitas responsabilidades.
- `WEB/index.html` segue como frontend único sem modularização.
- A suíte de testes automatizados precisa expansão (principalmente para fluxo distribuído OPENBOT ↔ HVM API).

---

## Roadmap sugerido pós-5.1

- `openbot.py` em módulos (`api/`, `tools/`, `security/`, `memory/`).
- RBAC/ABAC para ferramentas perigosas.
- Observabilidade (métricas/traces) no tráfego OPENBOT ↔ HVM API.
- Testes de integração para `/api/tools/execute/hvm_*` com mock do serviço 7777.
