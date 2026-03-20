import logging
from quart import Blueprint, request, jsonify, current_app, Response
from auth_system import require_auth
from core.streaming import sse_event, stream_text_chunks

chat_bp = Blueprint('chat', __name__)

@chat_bp.route("/clear", methods=["POST"])
@require_auth()
async def chat_clear():
    """
    Limpa o histórico de conversa do usuário (nova conversa).
    Não apaga memórias de longo prazo, apenas o histórico atual.
    """
    memory_agent = current_app.config.get("memory_agent")
    user_data = request.user_data
    username  = user_data['username']
    cleared   = memory_agent.clear_chat_history(username)
    return jsonify({
        "status":  "success",
        "message": f"Histórico limpo ({cleared} mensagens removidas).",
        "user":    username
    })

@chat_bp.route("", methods=["POST"])
@require_auth()
async def chat():
    """Chat com resposta completa"""
    agent_loop = current_app.config.get("agent_loop_func")
    active_provider_name = current_app.config.get("ACTIVE_PROVIDER_NAME")
    model = current_app.config.get("MODEL")
    
    user_data = request.user_data
    data      = await request.get_json()
    message   = data.get("message", "").strip()

    if not message:
        return jsonify({"error": "Mensagem vazia"}), 400

    responses = []
    try:
        async for response in agent_loop(user_data['username'], message):
            responses.append(response)
    except Exception as e:
        logging.exception("Erro no endpoint /api/chat")
        return jsonify({
            "error": "Falha ao processar a mensagem.",
            "details": str(e)[:180],
            "provider": active_provider_name,
        }), 500

    return jsonify({
        "status":    "success",
        "user":      user_data['username'],
        "provider":  active_provider_name,
        "model":     model,
        "responses": responses
    })

@chat_bp.route("/stream", methods=["POST"])
@require_auth()
async def chat_stream():
    """Chat com streaming SSE"""
    agent_loop = current_app.config.get("agent_loop_func")
    active_provider_name = current_app.config.get("ACTIVE_PROVIDER_NAME")
    model = current_app.config.get("MODEL")
    
    user_data = request.user_data
    data      = await request.get_json()
    message   = data.get("message", "").strip()

    if not message:
        return jsonify({"error": "Mensagem vazia"}), 400

    async def event_stream():
        yield sse_event({
            "type": "start",
            "provider": active_provider_name,
            "model": model,
        })
        try:
            async for response in agent_loop(user_data['username'], message):
                if response.get("type") == "final":
                    response_text = response.get("response", "")
                    async for chunk in stream_text_chunks(response_text, chunk_size=28):
                        yield sse_event(chunk)
                    yield sse_event(response)
                else:
                    yield sse_event(response)
        except Exception as e:
            logging.exception("Erro no endpoint /api/chat/stream")
            yield sse_event({
                "type": "error",
                "error": "Falha durante o streaming.",
                "details": str(e)[:180],
                "provider": active_provider_name,
            })
        finally:
            yield sse_event({"type": "done"})

    return Response(event_stream(), mimetype="text/event-stream")
