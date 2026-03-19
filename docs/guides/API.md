# API

## Endpoints públicos

- `POST /api/auth/register`
- `POST /api/auth/login`

## Endpoints protegidos

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

## Streaming SSE

O endpoint `/api/chat/stream` envia eventos com os tipos:

- `start`
- `chunk`
- `final`
- `error`
- `done`

O frontend foi preparado para tolerar falhas intermediárias sem quebrar a sessão visual.
