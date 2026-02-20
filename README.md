# 🤖 OPENBOT v3.1 — Documentação Técnica

> **Copyright (c) 2026 Rudjery** — Licenciado sob a [Apache License 2.0](http://www.apache.org/licenses/LICENSE-2.0)

Bem-vindo ao **OPENBOT v3.1**, uma plataforma de inteligência artificial autônoma e modular, projetada para ser o "canivete suíço" da automação e processamento de dados. Este documento detalha a arquitetura, funcionalidades e capacidades do sistema, com foco em **Memória**, **Escalabilidade** e **Portabilidade Universal**.

---

## 🧠 Sistema de Memória HGR (Hierarchical Graded Recall)

O OPENBOT implementa o **HGR — Hierarchical Graded Recall**, um sistema de memória em três níveis inspirado no funcionamento da memória humana. Diferente de agentes que apenas passam o histórico bruto ao LLM, o HGR seleciona, prioriza e persiste informação de forma inteligente.

### Os Três Níveis de Memória

| Nível | Tecnologia | TTL | Capacidade | Uso |
| :--- | :--- | :--- | :--- | :--- |
| **Short-term** | RAM (dict Python) | 1 hora | 30 entradas | Contexto imediato |
| **Medium-term** | RAM (sessão) | 24 horas | 100 entradas | Sessão do utilizador |
| **Long-term** | SQLite (disco) | Permanente | Ilimitado | Conhecimento persistente |

### Como o HGR Funciona na Prática

Quando o utilizador envia uma mensagem, o agente executa o seguinte fluxo:

*   **Passo 1:** A mensagem entra no short-term (RAM). Acesso instantâneo, zero I/O.
*   **Passo 2:** O sistema calcula a pontuação de importância (0.0 a 1.0). Acima de 0.3 vai para medium-term.
*   **Passo 3:** Ao fim da sessão ou por relevância, memórias importantes são gravadas no SQLite (long-term).
*   **Passo 4:** Na próxima conversa, o contexto relevante é recuperado do disco e injetado no system prompt.

**Resultado Medido em Produção:** Com `chat_history_to_llm = 40`, o agente mantém contexto das últimas 40 mensagens sem aumentar o consumo de RAM de forma significativa. O SQLite garante que informações críticas (preferências, projetos, configurações) sobrevivem a reinicializações.

### Configuração Atual dos Parâmetros

```python
mem_config = MemoryConfig(
    short_term_size = 30, # entradas em RAM (curto prazo)
    short_term_ttl = 3600, # 1 hora antes de expirar
    medium_term_ttl = 86400, # 24 horas (sessão)
    importance_threshold= 0.3, # limiar para persistir
    min_relevance_score = 0.1, # mínimo para recuperar
    max_chat_history = 100, # máx msgs armazenadas
    chat_history_to_llm = 40 # msgs enviadas ao LLM
)
```

### Por Que Isso Importa

A maioria dos agentes open-source simplesmente envia todo o histórico ao LLM em cada requisição. Isso tem dois problemas sérios:

*   **Custo de tokens:** Históricos longos consomem tokens caros em cada chamada.
*   **Falta de persistência:** Reiniciando o servidor, todo o contexto é perdido.
*   **Ruído:** Informações irrelevantes antigas degradam a qualidade das respostas.

O HGR resolve os três: usa tokens apenas com contexto relevante, persiste no SQLite e filtra por importância.

---

## 🚀 Escalabilidade

Com ~20 MB de RAM por instância e arquitetura assíncrona (Quart + asyncio), o OPENBOT foi projetado para escalar verticalmente e horizontalmente sem alterações estruturais.

### Cenários de Escala

| Hardware | RAM Disponível | Instâncias OPENBOT | Caso de Uso |
| :--- | :--- | :--- | :--- |
| Android (Termux) | 3–4 GB | ~15–20 | Servidor pessoal portátil |
| Raspberry Pi 4 | 4 GB | ~20–30 | Servidor doméstico 24/7 |
| VPS básico (€3/mês) | 1 GB | ~5–10 | Produção low-cost |
| VPS médio (€10/mês) | 4 GB | ~40–60 | Pequena equipa |
| Servidor dedicado | 32 GB | ~300–500 | Comunidade / Escala |

### O Que Torna Isso Possível

*   **Assíncrono por natureza:** Quart + asyncio permitem centenas de requisições simultâneas num único processo sem bloqueio.
*   **Thread pool + Process pool:** Ferramentas pesadas (execução de código, I/O) rodam em workers separados, sem bloquear o event loop.
*   **SQLite sem servidor:** Zero overhead de conexão a base de dados externa. Um ficheiro, acesso direto.
*   **Sem dependências pesadas:** Nenhum Docker, nenhum Redis, nenhuma fila de mensagens. Python puro.
*   **JWT stateless:** Autenticação não requer estado centralizado — cada token é auto-suficiente.

### Comparação com Projetos Similares

| Agente / Sistema | RAM Usada | Linhas Código | Android | Memória Persistente |
| :--- | :--- | :--- | :--- | :--- |
| OpenClaw | ~1.000 MB | 430.000+ | ❌ | ✅ |
| nanobot (HKUDS) | ~100 MB | ~4.000 | ❌ | ✅ |
| LangChain Agent | ~300 MB | N/A | ❌ | Parcial |
| AutoGPT | ~500 MB | N/A | ❌ | Parcial |
| **OPENBOT v3.1** | **~20 MB** | **~2.500** | ✅ | ✅ (HGR 3 níveis) |

O OPENBOT usa 50x menos RAM que o nanobot e 50x menos que o OpenClaw, mantendo memória persistente real em 3 níveis — algo que nenhum dos dois oferece de forma nativa.

---

## 🌍 Portabilidade Universal

"Se tem Python, o OPENBOT funciona." Esta é a premissa central de design. Não há requisitos de sistema operativo, arquitetura de CPU, runtime específico ou ligação a internet obrigatória.

### Requisitos Mínimos

**Dependências Obrigatórias:** Python 3.8+ | `pip install quart aiohttp psutil bcrypt PyJWT` | ~50 MB de espaço em disco

### Ambientes Testados e Suportados

| Ambiente | Como Executar | RAM Necessária | Status |
| :--- | :--- | :--- | :--- |
| Android + Termux | `pkg install python && python OPENBOT.py` | ~50 MB livre | ✅ Verificado |
| Linux (qualquer distro) | `python3 OPENBOT.py` | ~30 MB livre | ✅ Verificado |
| Windows (WSL / nativo) | `python OPENBOT.py` | ~30 MB livre | ✅ Funcional |
| macOS | `python3 OPENBOT.py` | ~30 MB livre | ✅ Funcional |
| Raspberry Pi (ARM) | `python3 OPENBOT.py` | ~50 MB livre | ✅ Funcional |
| Pendrive / Cartão SD | Copia pasta + executa | ~50 MB livre | ✅ Portátil |
| VPS mínimo (512 MB) | Direto no servidor | ~50 MB livre | ✅ Produção |
| Docker (opcional) | `FROM python:3.11-slim` | ~80 MB imagem | ✅ Opcional |

### O Conceito do Pendrive

O OPENBOT foi pensado como uma ferramenta genuinamente portátil. O cenário prático é simples:

1.  Coloca a pasta do projeto num pendrive ou cartão SD.
2.  Liga o pendrive a qualquer máquina com Python instalado.
3.  Executa: `python OPENBOT.py`
4.  O agente está online em segundos, com toda a memória persistida no SQLite local.
5.  Retiras o pendrive — não ficou nenhum dado na máquina hospedeira.

**Privacidade por Design:** Todos os dados (memória, utilizadores, logs) ficam no SQLite dentro da pasta do projeto. Não há cloud, não há telemetria, não há dependência externa. O agente é completamente offline-first se não houver chamadas a LLMs externos.

---

## 🔄 Troca de Provider em Runtime

Um dos recursos mais importantes para portabilidade é a capacidade de trocar o LLM sem reiniciar o servidor:

```bash
# Trocar para Groq (gratuito) em runtime:
POST /api/provider/switch
{ "provider": "groq", "model": "llama-3.1-8b-instant" }

# Providers disponíveis:
# openai → GPT-4o-mini / GPT-4o
# deepseek → deepseek-chat / deepseek-coder
# groq → LLaMA 3.1 / Mixtral (plano gratuito disponível)
```

Isto significa que o mesmo agente pode funcionar sem custo usando o plano gratuito do Groq, ou com máxima qualidade usando GPT-4o — sem alterar uma única linha de código.

---

## 🎯 Posicionamento no Ecossistema

O OPENBOT preenche um nicho que os grandes projetos de agentes ignoram: hardware acessível, zero dependências, portabilidade real.

### O Nicho que Ninguém Ocupava

*   OpenClaw e AutoGPT foram construídos para máquinas poderosas com internet estável. Assumem npm, Node.js, servidores dedicados.
*   LangChain é um framework, não um agente. Requer integração extensa antes de ser útil.
*   nanobot é Node.js/TypeScript — não roda em Termux sem configuração complexa.
*   OPENBOT é Python puro, assíncrono, com memória real, ferramentas nativas, e cabe num pendrive.

### Para Quem Este Projeto Foi Feito

| Perfil | Benefício Direto |
| :--- | :--- |
| Programador individual | Agente pessoal no telemóvel, sem custos de servidor |
| Comunidades open-source | Deploy em qualquer hardware doado ou reciclado |
| Países em desenvolvimento | Sem dependência de infraestrutura cara ou estável |
| Investigação e educação | Agente completo para estudar IA sem hardware dedicado |
| Privacidade prioritária | 100% local, sem dados na cloud, sem telemetria |
| Developers sem budget | Groq gratuito + Termux = agente IA a custo zero |

"20 MB de RAM. Memória persistente. Roda em qualquer lugar. Se tem Python, o OPENBOT funciona."

---

## 🛠️ Instalação Rápida

```bash
chmod +x install.sh
./install.sh
```

O script automaticamente:

*   Verifica versão do Python (3.8+ requerido)
*   Cria ambiente virtual (opcional)
*   Instala dependências (`quart`, `hypercorn`, `openai`, `bcrypt`, `pyjwt`, `psutil`)
*   Configura o arquivo `.env` interativamente
*   Gera scripts `start.sh` e `backup.sh`

### Pré-requisitos

*   Python 3.8+
*   Chave de API de ao menos um provider (OpenAI, DeepSeek ou Groq)
*   Linux / Termux (Android) compatível

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

## 🔐 Segurança e Autenticação

O sistema conta com uma camada de segurança robusta baseada em **JWT (JSON Web Tokens)**:

*   **Hash de senhas com bcrypt** (rounds=12) — sem armazenamento de senhas em texto puro
*   **Rate limiting** — bloqueio automático após 5 tentativas falhas (15 min de lockout)
*   **Tokens revogáveis** — logout real via banco de revogação
*   **Validação de senha** — requisitos configuráveis (maiúsculas, dígitos, especiais)
*   **Rotas protegidas** com decorator `@require_auth()` e suporte a `admin_only=True`
*   **Sandbox de filesystem** — acesso restrito ao `BASE_DIR`

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

*   **Permissiva e amigável** — uso comercial e modificação são livres
*   **Proteção de patentes** — cobre inovações arquiteturais como o HGR Memory System
*   **Compatível com o ecossistema** — alinhada com projetos como LangChain, FastAPI e OpenClaw
*   **Atribuição garantida** — exige menção ao autor original em distribuições

Ao usar, modificar ou distribuir este projeto, mantenha os créditos ao autor original **Rudjery** e o aviso de licença Apache 2.0.

---

*Desenvolvido com foco em autonomia, velocidade e inteligência. Build freely. Innovate openly. 🚀*
