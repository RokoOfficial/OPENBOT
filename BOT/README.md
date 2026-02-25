# OPENBOT v4.0

**Assistente de IA com ferramentas, memória persistente e autenticação JWT.**

Multi-provider (OpenAI · DeepSeek · Groq · Anthropic) · 40 ferramentas · Memória HGR · API REST assíncrona

---

## Início Rápido

```bash
# 1. Instalar dependências
bash install.sh

# 2. Iniciar o servidor
python OPENBOT.py

# 3. Registrar e fazer login
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"usuario","password":"Senha@123","email":"eu@email.com"}'

curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"usuario","password":"Senha@123"}'

# 4. Usar o chat (substituir TOKEN pelo token recebido)
curl -X POST http://localhost:5000/api/chat \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Qual é o IP do google.com?"}'
```

---

## Estrutura do Projeto

```
OPENBOT.py          — Servidor principal (Quart + agent loop)
HGR.py              — Sistema de memória hierárquica (3 níveis)
auth_system.py      — Autenticação JWT + bcrypt
config.py           — Configuração centralizada
OPENBOT_CORS.py     — Entry point com CORS habilitado
install.sh          — Script de instalação automática
.env                — Variáveis de ambiente (criado pelo install.sh)
```

---

## Variáveis de Ambiente

| Variável | Descrição | Padrão |
|---|---|---|
| `OPENBOT_PROVIDER` | Provider ativo (`deepseek`, `groq`, `openai`, `anthropic`) | `deepseek` |
| `OPENBOT_MODEL` | Modelo LLM | Padrão do provider |
| `DEEPSEEK_API_KEY` | Chave DeepSeek | — |
| `GROQ_API_KEY` | Chave Groq | — |
| `OPENAI_API_KEY` | Chave OpenAI | — |
| `ANTHROPIC_API_KEY` | Chave Anthropic | — |
| `JWT_SECRET` | Segredo JWT (altere em produção!) | inseguro |
| `OPENBOT_ENV` | Ambiente (`development`, `production`, `testing`) | `development` |
| `OPENBOT_BASE_DIR` | Diretório de trabalho | `~/openbot_workspace` |
| `PORT` | Porta do servidor | `5000` |
| `CORS_ORIGINS` | Origens CORS permitidas | `*` |

---

## Endpoints

### Públicos
| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/auth/register` | Registrar usuário |
| POST | `/api/auth/login` | Login (retorna JWT) |

### Protegidos (requer `Authorization: Bearer <token>`)
| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/auth/logout` | Revogar token |
| POST | `/api/chat` | Chat com resposta completa |
| POST | `/api/chat/stream` | Chat com streaming SSE |
| POST | `/api/chat/clear` | Limpar histórico de conversa |
| GET  | `/api/provider/list` | Listar providers disponíveis |
| POST | `/api/provider/switch` | Trocar provider em runtime |
| GET  | `/api/tools/list` | Listar ferramentas |
| POST | `/api/tools/execute/<nome>` | Executar ferramenta diretamente |
| GET  | `/api/tools/history` | Histórico de execuções |
| GET  | `/api/user/profile` | Perfil e estatísticas |
| GET  | `/api/memory/stats` | Estatísticas de memória |

### Admin
| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/admin/stats` | Estatísticas globais do sistema |

---

## Ferramentas (40 total)

| Categoria | Ferramentas |
|---|---|
| Python (5) | `python_execute`, `python_eval`, `python_import`, `python_debug`, `python_format` |
| Shell (5) | `shell_execute`, `shell_script`, `shell_pipe`, `shell_env`, `shell_which` |
| Network (6) | `net_ping`, `net_dns`, `net_curl`, `net_ip_info`, `net_port_check`, `net_whois` |
| Filesystem (6) | `fs_read`, `fs_write`, `fs_list`, `fs_delete`, `fs_info`, `fs_search` |
| Data (5) | `data_parse_json`, `data_query_json`, `data_csv_to_json`, `data_sqlite`, `data_regex` |
| System (4) | `sys_info`, `sys_time`, `sys_uptime`, `sys_processes` |
| Crypto (3) | `crypto_hash`, `crypto_random`, `crypto_base64` |
| Utility (6) | `util_calc`, `util_uuid`, `util_timestamp`, `util_json_format`, `util_text_stats`, `util_sleep` |
| Memory (8) | `memory_store`, `memory_recall`, `memory_search`, `memory_update`, `memory_delete`, `memory_stats`, `memory_cleanup`, `memory_export` |

---

## Memória HGR (3 Níveis)

| Nível | Armazenamento | TTL | Uso |
|---|---|---|---|
| Short-term | RAM (deque) | 1 hora | Contexto imediato da sessão |
| Medium-term | RAM (sessão) | 24 horas | Contexto da sessão ativa |
| Long-term | SQLite | Permanente | Informações importantes entre sessões |

---

## Trocar Provider em Runtime

```bash
curl -X POST http://localhost:5000/api/provider/switch \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider": "groq", "model": "llama-3.1-70b-versatile"}'
```

---

## Dependências

```
quart>=0.19.4
quart-cors>=0.6.0
hypercorn>=0.16.0
openai==0.28.1
PyJWT>=2.8.0
bcrypt>=4.1.2
aiohttp>=3.9.0
psutil>=5.9.0
python-dotenv>=1.0.0
```
