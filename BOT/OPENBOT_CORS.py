# OPENBOT_CORS.py
# Arquivo para executar a API OPENBOT v3.0 com CORS liberado para todas as origens.

from OPENBOT import app
from quart_cors import cors
# 
# REGISTRO DAS TOOLS DE MEMÓRIA

from MEMORYSQL import register_memory_tools

# No startup, depois de criar o tool_registry:
#memory_tools = #register_memory_tools(tool_registry)



# Aplica CORS globalmente à aplicação Quart
# Para desenvolvimento: permite qualquer origem (*)
# Em produção, substitua "*" pela lista de origens confiáveis, ex: ["https://meusite.com"]
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

    print("🚀 Servidor OPENBOT v3.0 com CORS habilitado rodando em http://0.0.0.0:5000")
    asyncio.run(serve(app, config))