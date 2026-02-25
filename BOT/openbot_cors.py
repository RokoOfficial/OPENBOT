# ============================================================
# OPENBOT_CORS.py
# Entry point com CORS habilitado — importa do core modular
# ============================================================
# Para desenvolvimento: allow_origin="*"
# Para produção: allow_origin=["https://meusite.com", "https://app.meusite.com"]
# ============================================================

from openbot import app
from quart_cors import cors

# Aplica CORS globalmente
app = cors(app, allow_origin="*")

if __name__ == "__main__":
    import asyncio
    from hypercorn.config import Config
    from hypercorn.asyncio import serve

    config = Config()
    config.bind = ["0.0.0.0:5000"]
    config.use_reloader = False
    config.accesslog = "-"
    config.errorlog = "-"

    print("🚀 OPENBOT v3.0 com CORS habilitado → http://0.0.0.0:5000")
    asyncio.run(serve(app, config))
