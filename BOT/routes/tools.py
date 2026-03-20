from quart import Blueprint, request, jsonify, current_app
from auth_system import require_auth

tools_bp = Blueprint('tools', __name__)

@tools_bp.route("/list", methods=["GET"])
@require_auth()
async def tools_list():
    tool_registry = current_app.config.get("tool_registry")
    return jsonify({
        "status": "success",
        "total":  len(tool_registry.list_tools()),
        "tools":  tool_registry.list_tools()
    })

@tools_bp.route("/execute/<tool_name>", methods=["POST"])
@require_auth()
async def tools_execute(tool_name):
    tool_engine = current_app.config.get("tool_engine")
    user_data = request.user_data
    data      = await request.get_json()
    args      = data.get("args", [])
    kwargs    = data.get("kwargs", {})

    result = await tool_engine.execute(tool_name, user_data['username'], *args, **kwargs)
    return jsonify({"status": "success", "result": result})

@tools_bp.route("/history", methods=["GET"])
@require_auth()
async def tools_history():
    tool_engine = current_app.config.get("tool_engine")
    user_data = request.user_data
    username  = user_data['username']
    history   = tool_engine.execution_history.get(username, [])
    return jsonify({
        "status":  "success",
        "total":   len(history),
        "history": history[-50:]
    })
