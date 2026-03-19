# Plano de Refatoração do OPENBOT

## Objetivo

Transformar o OPENBOT de um backend funcional, porém concentrado em arquivos grandes, em uma base modular, testável e segura.

---

## Fase 1 — saneamento e base compartilhada

### Entregue nesta etapa

- centralização de providers e leitura de ambiente em `BOT/openbot_shared.py`;
- alinhamento de host/porta/CORS entre entrypoints;
- atualização do instalador para trabalhar a partir da raiz do projeto;
- documentação principal reescrita para refletir o estado real do repositório.

### Benefícios

- reduz duplicação de configuração;
- cria uma fonte única para providers e defaults de ambiente;
- prepara extrações futuras sem quebrar o entrypoint atual.

---

## Fase 2 — modularização do backend

### Meta

Extrair responsabilidades hoje concentradas em `BOT/openbot.py`.

### Estrutura alvo sugerida

```text
BOT/
├── app.py
├── providers.py
├── routes/
│   ├── auth.py
│   ├── chat.py
│   ├── memory.py
│   ├── providers.py
│   └── crons.py
├── services/
│   ├── agent.py
│   ├── memory.py
│   └── tools.py
├── core/
│   ├── settings.py
│   ├── logging.py
│   └── security.py
└── ...
```

### Ordem sugerida

1. extrair `providers.py`;
2. extrair `routes/provider` e `routes/auth`;
3. extrair boot do app para `app.py`;
4. migrar orquestração do agente para `services/agent.py`.

---

## Fase 3 — frontend

### Meta

Quebrar `WEB/index.html` em partes menores.

### Estrutura alvo sugerida

```text
WEB/
├── index.html
└── assets/
    ├── app.js
    ├── api.js
    ├── auth.js
    ├── chat.js
    ├── memory.js
    ├── crons.js
    └── styles.css
```

---

## Fase 4 — qualidade e operação

### Itens prioritários

- testes unitários e de integração;
- healthcheck e readiness endpoint;
- logs estruturados;
- CI com lint + compile + tests;
- `.env.example` sem segredos;
- política de defaults seguros para produção.

---

## Critérios de sucesso

- configuração central sem duplicação;
- entrypoints pequenos e previsíveis;
- rotas separadas por domínio;
- frontend modular;
- documentação consistente com o código;
- cobertura mínima de testes para auth, config, HGR e endpoints essenciais.
