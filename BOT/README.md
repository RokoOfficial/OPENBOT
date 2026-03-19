# BOT / Backend OPENBOT

Este diretório concentra o backend do OPENBOT.

## Organização atual

- `core/`: helpers reutilizáveis de providers e streaming.
- `routes/`: pasta preparada para extração progressiva das rotas.
- `openbot.py`: entrypoint principal atual.
- `openbot_cors.py`: entrypoint com CORS habilitado.
- `openbot_shared.py`: leitura de `.env` e defaults compartilhados.
- `config.py`: configuração tipada.
- `auth_system.py`: autenticação.
- `HGR.py`: memória persistente.

## Objetivo desta fase

Esta fase moveu os primeiros blocos reutilizáveis para `core/` e deixou a base pronta para extração gradual das rotas e serviços restantes.
