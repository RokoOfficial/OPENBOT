# 🤖 OpenBot v3.1 — Plug & Play Agent Architecture with Tool Use

> **Copyright (c) 2026 Rudjery** — Licensed under the [Apache License 2.0](http://www.apache.org/licenses/LICENSE-2.0)

Bem-vindo ao **OpenBot v3.1**, uma plataforma de inteligência artificial autônoma e modular, projetada para ser o "canivete suíço" da automação e processamento de dados. Este projeto representa uma evolução significativa na integração entre Modelos de Linguagem de Grande Escala (LLMs) e a execução de ferramentas em tempo real.

> **Nota de Crédito:** Esta versão v3.1 foi desenvolvida e expandida por **Rudjery (RokoOfficial)**, introduzindo a arquitetura HGR Memory de três níveis, 40 ferramentas integradas, suporte multi-provider e autenticação JWT nativa.

---

## 🚀 Visão Geral

O OpenBot não é apenas um chatbot — é um **Agente Autônomo** capaz de interagir com o sistema operacional, executar código, gerenciar bancos de dados e realizar operações de rede complexas. Com suporte nativo a **OpenAI (GPT)**, **DeepSeek** e **Groq (LLaMA/Mixtral)**, o OpenBot adapta-se ao provedor que melhor atende às suas necessidades, com troca em runtime sem reinicialização.

Com ~4.000 linhas de código elegante, entrega o que projetos similares fazem com 150.000+ linhas.

---

## 🧠 Arquitetura de Memória HGR (3 Níveis)

Diferente de sistemas convencionais, o OpenBot utiliza o sistema **HGR (Hierarchical Grounded Reasoning) Memory**, que organiza o conhecimento em três camadas independentes:

| Nível | Tipo | TTL | Armazenamento |
| :--- | :--- | :--- | :--- |
| **Short-Term** | Contexto imediato da conversa | 1 hora | RAM (deque) |
| **Medium-Term** | Sessão ativa do usuário | 24 horas | RAM (sessão) |
| **Long-Term** | Fatos, preferências, aprendizados | Persistente | SQLite |

O sistema usa pontuação de importância automática para decidir o que merece ser promovido à memória de longo prazo, com threshold configurável.

---

## 🛠️ Arsenal de Ferramentas (40 Ferramentas)

O OpenBot vem equipado com um registro central de ferramentas divididas em categorias estratégicas:

| Categoria | Qtd | Exemplos |
| :--- | :---: | :--- |
| **Python** | 5 | `python_execute`, `python_debug`, `python_inspect` |
| **Shell** | 5 | `shell_execute`, `shell_script`, `shell_process_list` |
| **Network** | 6 | `curl_request`, `http_download`, `port_scan`, `dns_lookup` |
| **Filesystem** | 5 | `file_read`, `file_write`, `file_list`, `file_info` |
| **Data** | 4 | `data_parse_json`, `data_sqlite_query`, `data_csv_to_json` |
| **System** | 3 | `system_info`, `system_time`, `system_uptime` |
| **Crypto** | 2 | `crypto_hash`, `crypto_random` |
| **Utility** | 4 | `util_calc`, `util_uuid`, `util_base64_encode` |
| **Memory** | 8 | `memory_store`, `memory_recall`, `memory_search`, `memory_export` |

> Todas as ferramentas de filesystem e SQLite operam com sandbox restrita ao `BASE_DIR`, garantindo isolamento de segurança.

---

## 🌐 Multi-Provider: OpenAI · DeepSeek · Groq

Configure via variável de ambiente ou troque em runtime via API:

```bash
# Configurar provider padrão
export OPENBOT_PROVIDER=groq
export GROQ_API_KEY=sua_chave_aqui
export OPENBOT_MODEL=llama-3.1-70b-versatile

# Ou use DeepSeek
export OPENBOT_PROVIDER=deepseek
export DEEPSEEK_API_KEY=sua_chave_aqui
```

```bash
# Trocar provider em runtime (sem reiniciar o servidor)
curl -X POST http://localhost:5000/api/provider/switch \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"provider": "groq", "model": "llama-3.1-8b-instant"}'
```

---

## 🔐 Segurança e Autenticação

O sistema conta com uma camada de segurança robusta baseada em **JWT (JSON Web Tokens)**:

- **Hash de senhas com bcrypt** (rounds=12) — sem armazenamento de senhas em texto puro
- **Rate limiting** — bloqueio automático após 5 tentativas falhas (15 min de lockout)
- **Tokens revogáveis** — logout real via banco de revogação
- **Validação de senha** — requisitos configuráveis (maiúsculas, dígitos, especiais)
- **Rotas protegidas** com decorator `@require_auth()` e suporte a `admin_only=True`
- **Sandbox de filesystem** — acesso restrito ao `BASE_DIR`

---

## 📂 Estrutura do Projeto

```text
OPENBOT/
├── OPENBOT.py          # Núcleo do agente + API REST (Quart/Hypercorn)
├── HGR.py              # Motor de Memória Hierárquica (3 níveis)
├── auth_system.py      # Autenticação JWT + Rate Limiting
├── config.py           # Configurações centralizadas (multi-provider)
├── OPENBOT_CORS.py     # Entry point com CORS habilitado
├── install.sh          # Script de instalação automatizada
├── test_api.py         # Suite de testes automatizados
└── README.md           # Esta documentação
```

---

## 🛠️ Instalação Rápida

```bash
chmod +x install.sh
./install.sh
```

O script automaticamente:
- Verifica versão do Python (3.8+ requerido)
- Cria ambiente virtual (opcional)
- Instala dependências (`quart`, `hypercorn`, `openai`, `bcrypt`, `pyjwt`, `psutil`)
- Configura o arquivo `.env` interativamente
- Gera scripts `start.sh` e `backup.sh`

### Pré-requisitos

- Python 3.8+
- Chave de API de ao menos um provider (OpenAI, DeepSeek ou Groq)
- Linux / Termux (Android) compatível

### Iniciar o servidor

```bash
./start.sh
# ou com CORS habilitado:
python3 OPENBOT_CORS.py
```

---

## 🔌 Endpoints da API

| Método | Rota | Acesso | Descrição |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Público | Status e informações do servidor |
| `POST` | `/api/auth/register` | Público | Registrar novo usuário |
| `POST` | `/api/auth/login` | Público | Login e obtenção de token JWT |
| `POST` | `/api/auth/logout` | Auth | Revogar token |
| `POST` | `/api/chat` | Auth | Chat com resposta completa |
| `POST` | `/api/chat/stream` | Auth | Chat com streaming SSE |
| `POST` | `/api/chat/clear` | Auth | Limpar histórico de conversa |
| `GET` | `/api/provider/list` | Auth | Listar providers disponíveis |
| `POST` | `/api/provider/switch` | Auth | Trocar provider em runtime |
| `GET` | `/api/tools/list` | Auth | Listar ferramentas disponíveis |
| `POST` | `/api/tools/execute/:name` | Auth | Executar ferramenta diretamente |
| `GET` | `/api/tools/history` | Auth | Histórico de execuções |
| `GET` | `/api/user/profile` | Auth | Perfil e estatísticas do usuário |
| `GET` | `/api/admin/stats` | Admin | Estatísticas globais do sistema |

### Exemplo de uso rápido

```bash
# 1. Registrar usuário
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","email":"admin@example.com","password":"Admin123!"}'

# 2. Login
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin123!"}'

# 3. Chat (com token retornado no login)
curl -X POST http://localhost:5000/api/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message":"Qual é o IP do google.com?"}'
```

---

## 🧪 Testes

Execute a suite de testes automatizados (requer servidor rodando):

```bash
python3 test_api.py
```

A suite cobre: registro de usuário, login válido/inválido, rejeição de senha fraca, acesso autenticado ao perfil, envio de mensagem ao agente, bloqueio de acesso sem token, logout e rejeição de token inválido.

---

## 📄 Licença

```
Copyright (c) 2026 Rudjery

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

### Por que Apache 2.0?

A **Apache License 2.0** foi escolhida por oferecer o melhor equilíbrio entre abertura e proteção:

- **Permissiva e amigável** — uso comercial e modificação são livres
- **Proteção de patentes** — cobre inovações arquiteturais como o HGR Memory System
- **Compatível com o ecossistema** — alinhada com projetos como LangChain, FastAPI e OpenClaw
- **Atribuição garantida** — exige menção ao autor original em distribuições

Ao usar, modificar ou distribuir este projeto, mantenha os créditos ao autor original **Rudjery** e o aviso de licença Apache 2.0.

---

*Desenvolvido com foco em autonomia, velocidade e inteligência. Build freely. Innovate openly. 🚀*
