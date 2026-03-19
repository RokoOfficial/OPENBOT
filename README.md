<p align="center">
  <img src="assets/logo.png" alt="OPENBOT Logo" width="320">
</p>

# OPENBOT

Backend assíncrono em Python para um agente com autenticação JWT, memória HGR persistente, múltiplos provedores de LLM e interface web estática.

> **Estado atual:** o projeto está em uma **refatoração incremental**. O core funcional continua concentrado em `BOT/openbot.py`, enquanto a configuração compartilhada começou a ser extraída para módulos reutilizáveis.

---

## Visão geral

O OPENBOT combina quatro blocos principais:

1. **API assíncrona** com Quart/Hypercorn.
2. **Memória HGR** persistente com SQLite.
3. **Autenticação** com JWT + bcrypt.
4. **Frontend web** em `WEB/index.html`.

### Stack atual

- Python 3.8+
- Quart + Hypercorn
- SQLite
- JWT / bcrypt
- `openai==0.28.1` com compat layer para OpenAI, DeepSeek e Groq
- Tailwind via CDN no frontend

---

## Estrutura do projeto

```text
OPENBOT/
├── assets/
│   └── logo.png
├── BOT/
│   ├── openbot.py          # servidor principal atual (monolítico)
│   ├── openbot_cors.py     # entrypoint com CORS
│   ├── openbot_shared.py   # NOVO: configuração compartilhada/providers
│   ├── HGR.py              # memória persistente e cron jobs
│   ├── auth_system.py      # autenticação JWT + bcrypt
│   ├── config.py           # config tipada para ambientes
│   ├── install.sh          # instalação guiada
│   └── README.md
├── WEB/
│   └── index.html          # frontend atual (arquivo único)
├── docs/
│   ├── HGR_PT.md
│   ├── HGR_EN.md
│   ├── HGR_ES.md
│   └── REFATORACAO.md      # NOVO: plano técnico da refatoração
├── LICENSE
└── README.md
```

---

## Início rápido

### 1. Instalação

```bash
bash BOT/install.sh
```

### 2. Subir o servidor principal

```bash
python BOT/openbot.py
```

### 3. Subir com CORS habilitado

```bash
python BOT/openbot_cors.py
```

### 4. Fluxo básico de autenticação

```bash
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"usuario","password":"Senha@123","email":"eu@email.com"}'

curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"usuario","password":"Senha@123"}'
```

---

## Variáveis de ambiente

| Variável | Descrição | Padrão |
|---|---|---|
| `OPENBOT_PROVIDER` | Provider ativo (`deepseek`, `groq`, `openai`) | `deepseek` |
| `OPENBOT_MODEL` | Modelo LLM | default do provider |
| `DEEPSEEK_API_KEY` | Chave DeepSeek | — |
| `GROQ_API_KEY` | Chave Groq | — |
| `OPENAI_API_KEY` | Chave OpenAI | — |
| `JWT_SECRET` | Segredo JWT | obrigatório em produção |
| `OPENBOT_ENV` | `development`, `testing`, `production` | `development` |
| `OPENBOT_BASE_DIR` | diretório de trabalho do agente | `~/openbot_workspace` |
| `HOST` | host HTTP | `0.0.0.0` |
| `PORT` | porta HTTP | `5000` |
| `CORS_ORIGINS` | `*` ou lista separada por vírgula | `*` |

---

## Endpoints principais

### Públicos

- `POST /api/auth/register`
- `POST /api/auth/login`

### Protegidos

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

---

## Situação da refatoração

### Já iniciado nesta etapa

- extração de configuração compartilhada para `BOT/openbot_shared.py`;
- alinhamento inicial entre `openbot.py`, `config.py` e `openbot_cors.py`;
- correções de documentação e do fluxo de instalação.

### Próximos passos

Veja `docs/REFATORACAO.md` para o plano técnico detalhado.

---

## Segurança

- **Não** suba segredos reais para o repositório.
- Em produção, defina `JWT_SECRET` forte.
- Restrinja `CORS_ORIGINS` para seus domínios.
- Rotacione imediatamente qualquer token exposto acidentalmente.

---

## Limitações atuais conhecidas

- `BOT/openbot.py` ainda concentra boa parte da aplicação.
- `WEB/index.html` ainda é um frontend monolítico com HTML/CSS/JS inline.
- A camada de providers ainda depende da estratégia atual baseada em `openai==0.28.1`.
- A suíte de testes automatizados ainda precisa ser expandida.
