# Arquitetura

## Camadas

### 1. Entry points

- `BOT/openbot.py`
- `BOT/openbot_cors.py`

### 2. Core

- `BOT/core/providers.py`: registro de providers e chamada ao LLM.
- `BOT/core/streaming.py`: helpers de SSE e chunking resiliente.
- `BOT/openbot_shared.py`: leitura de ambiente e defaults compartilhados.

### 3. Domínio

- `BOT/auth_system.py`
- `BOT/HGR.py`
- `BOT/config.py`

### 4. Frontend

- `WEB/index.html`

## Direção da refatoração

O objetivo é que `openbot.py` fique progressivamente menor, delegando providers, streaming, rotas e serviços para submódulos dedicados.
