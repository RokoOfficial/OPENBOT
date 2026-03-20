from quart import Blueprint, request, jsonify, current_app
from auth_system import require_auth, get_client_ip

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/register", methods=["POST"])
async def register():
    auth_manager = current_app.config["auth_manager"]
    data = await request.get_json()
    if not data:
        return jsonify({"error": "JSON inválido ou ausente"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    email    = data.get("email", "").strip()

    if not all([username, password, email]):
        return jsonify({"error": "username, password e email são obrigatórios"}), 400

    success, message, user_data = auth_manager.register_user(username, email, password)

    if success:
        return jsonify({
            "status":  "success",
            "message": message,
            "user": {
                "user_id":  user_data["user_id"],
                "username": user_data["username"],
                "email":    user_data["email"]
            }
        })
    return jsonify({"error": message}), 400

@auth_bp.route("/login", methods=["POST"])
async def login():
    auth_manager = current_app.config["auth_manager"]
    data = await request.get_json()
    if not data:
        return jsonify({"error": "JSON inválido ou ausente"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    ip       = get_client_ip(request)

    if not all([username, password]):
        return jsonify({"error": "username e password são obrigatórios"}), 400

    success, message, token = auth_manager.login(username, password, ip)

    if success:
        return jsonify({
            "status":   "success",
            "token":    token,
            "username": username,
            "message":  message
        })
    return jsonify({"error": message}), 401

@auth_bp.route("/logout", methods=["POST"])
@require_auth()
async def logout():
    auth_manager = current_app.config["auth_manager"]
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    auth_manager.revoke_token(token)
    return jsonify({"status": "success", "message": "Logout realizado."})
