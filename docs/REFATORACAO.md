# Plano de Refatoração do OPENBOT

## Objetivo

Evoluir o OPENBOT para uma base modular, resiliente a falhas de streaming e organizada em camadas claras de backend, core e documentação.

---

## Fase entregue nesta iteração

### Estrutura criada

- `BOT/core/providers.py`
- `BOT/core/streaming.py`
- `BOT/routes/`
- `docs/guides/`

### Mudanças implementadas

- providers agora restritos a **DeepSeek**, **OpenAI** e **Anthropic**;
- streaming SSE reforçado no backend e no frontend;
- streaming passou a ser o modo padrão da interface;
- erro de stream não derruba mais a UI nem quebra a sessão;
- documentação reestruturada em guias técnicos e operacionais.

---

## Próximas fases

### Fase 2 — extração de rotas

Objetivo: mover endpoints de `openbot.py` para `BOT/routes/`.

Ordem sugerida:

1. `providers.py`
2. `auth.py`
3. `chat.py`
4. `memory.py`
5. `crons.py`

### Fase 3 — extração de serviços

Objetivo: separar a lógica do agente e da memória em `services/`.

### Fase 4 — frontend modular

Objetivo: quebrar `WEB/index.html` em assets dedicados de JS/CSS.

---

## Resultado esperado

- backend modular e testável;
- providers desacoplados do entrypoint principal;
- streaming resiliente e observável;
- documentação profissional e consistente;
- base pronta para CI/testes e evolução incremental.
