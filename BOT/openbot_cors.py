# ============================================================
# OPENBOT_CORS.py
# Entry point com CORS habilitado — importa do core modular
# ============================================================
# Para desenvolvimento: allow_origin="*"
# Para produção: allow_origin=["https://meusite.com", "https://app.meusite.com"]
# ============================================================

from openbot import app
from openbot_shared import get_cors_origins, get_server_host, get_server_port
from quart_cors import cors

# Aplica CORS globalmente
cors_origins = get_cors_origins()
app = cors(app, allow_origin=cors_origins if cors_origins != ["*"] else "*")

if __name__ == "__main__":
    import asyncio
    from hypercorn.config import Config
    from hypercorn.asyncio import serve

    config = Config()
    config.bind = [f"{get_server_host()}:{get_server_port()}"]
    config.use_reloader = False
    config.accesslog = "-"
    config.errorlog = "-"

    print(f"🚀 OPENBOT com CORS habilitado → http://{get_server_host()}:{get_server_port()}")
    asyncio.run(serve(app, config))
