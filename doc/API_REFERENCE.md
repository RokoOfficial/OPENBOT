# OPENBOT API Reference v3.1

O OPENBOT oferece uma API RESTful para integração e comunicação com o agente.

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
