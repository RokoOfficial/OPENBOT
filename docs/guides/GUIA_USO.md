# Guia de Uso

## Instalação

```bash
bash BOT/install.sh
```

## Subir o servidor

```bash
python BOT/openbot.py
```

## Fluxo básico

1. registrar usuário;
2. fazer login;
3. enviar mensagem no chat;
4. usar streaming como modo padrão;
5. trocar provider em tempo de execução, se necessário.

## Observações

- o chat abre em modo streaming por padrão;
- se o stream falhar, a interface tenta encerrar o fluxo sem quebrar o chat;
- CORS deve ser restringido em produção.
