import os
from quart import Blueprint, request, jsonify, current_app
from auth_system import require_auth
from core.providers import PROVIDERS

provider_bp = Blueprint('provider', __name__)

@provider_bp.route("/list", methods=["GET"])
@require_auth()
async def provider_list():
    """Lista todos os providers e seus modelos"""
    # Importar globais do app via current_app ou passar via config
    active_provider_name = current_app.config.get("ACTIVE_PROVIDER_NAME")
    model = current_app.config.get("MODEL")
    
    providers_info = []
    for name, p in PROVIDERS.items():
        key_ok = bool(os.environ.get(p["api_key_env"], "").strip())
        providers_info.append({
            "name":          name,
            "label":         p["label"],
            "api_base":      p["api_base"],
            "api_key_env":   p["api_key_env"],
            "api_key_set":   key_ok,
            "models":        p["models"]["available"],
            "default_model": p["models"]["default"],
            "active":        name == active_provider_name
        })
    return jsonify({
        "status":           "success",
        "active_provider":  active_provider_name,
        "active_model":     model,
        "providers":        providers_info
    })

@provider_bp.route("/switch", methods=["POST"])
@require_auth()
async def provider_switch():
    """
    Troca provider em runtime.
    Body: {"provider": "anthropic", "model": "claude-3-5-haiku-latest"}
    """
    data          = await request.get_json()
    provider_name = data.get("provider", "").strip().lower()
    model         = data.get("model", "").strip() or None

    if not provider_name:
        return jsonify({"error": "Campo 'provider' obrigatório"}), 400

    try:
        # Chama a função switch_provider que deve estar no app ou em um helper
        switch_func = current_app.config.get("switch_provider_func")
        if not switch_func:
            return jsonify({"error": "Função de troca de provider não configurada"}), 500
            
        result = switch_func(provider_name, model)
        return jsonify({"status": "success", **result})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
