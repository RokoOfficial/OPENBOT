# BOT / Core do OPENBOT

Este diretório contém o backend principal do OPENBOT.

## Arquivos principais

- `openbot.py`: servidor atual e orquestração principal.
- `openbot_cors.py`: inicialização com CORS configurável por ambiente.
- `openbot_shared.py`: configuração compartilhada de providers, host, porta e CORS.
- `config.py`: configuração tipada por ambiente.
- `auth_system.py`: autenticação JWT e banco de usuários.
- `HGR.py`: memória persistente e cron jobs.
- `install.sh`: script de instalação.

## Execução

```bash
python BOT/openbot.py
```

Ou com CORS:

```bash
python BOT/openbot_cors.py
```

## Objetivo da refatoração em andamento

O alvo é reduzir o acoplamento atual do `openbot.py`, movendo gradualmente responsabilidades para módulos específicos de configuração, providers, rotas e serviços.
