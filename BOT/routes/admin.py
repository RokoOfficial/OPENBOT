import os
from quart import Blueprint, request, jsonify, current_app
from auth_system import require_auth

admin_bp = Blueprint('admin', __name__)

@admin_bp.route("/user/profile", methods=["GET"])
@require_auth()
async def user_profile():
    memory_agent = current_app.config.get("memory_agent")
    memory_sql = current_app.config.get("memory_sql")
    tool_engine = current_app.config.get("tool_engine")
    active_provider_name = current_app.config.get("ACTIVE_PROVIDER_NAME")
    model = current_app.config.get("MODEL")
    
    user_data    = request.user_data
    stats        = memory_agent.get_stats(user_data['username'])
    memory_stats = await memory_sql.memory_stats(user_data['username'])
    tool_stats   = {
        "total_executions": len(tool_engine.execution_history.get(user_data['username'], [])),
        "recent_tools": [
            {"tool": h['tool'], "time": h['time'], "timestamp": h['timestamp']}
            for h in tool_engine.execution_history.get(user_data['username'], [])[-5:]
        ]
    }
    return jsonify({
        "status": "success",
        "user": {
            "user_id":  user_data['user_id'],
            "username": user_data['username'],
            "email":    user_data['email'],
            "is_admin": user_data.get('is_admin', False)
        },
        "provider": {
            "active": active_provider_name,
            "model":  model
        },
        "memory_stats":      stats,
        "tool_stats":        tool_stats,
        "persistent_memory": memory_stats.get('stats', {}) if memory_stats['status'] == 'success' else {}
    })

@admin_bp.route("/stats", methods=["GET"])
@require_auth(admin_only=True)
async def admin_stats():
    memory_sql = current_app.config.get("memory_sql")
    tool_engine = current_app.config.get("tool_engine")
    tool_registry = current_app.config.get("tool_registry")
    active_provider_name = current_app.config.get("ACTIVE_PROVIDER_NAME")
    model = current_app.config.get("MODEL")
    base_dir = current_app.config.get("BASE_DIR")
    thread_pool = current_app.config.get("thread_pool")
    process_pool = current_app.config.get("process_pool")
    get_resource_usage = current_app.config.get("get_resource_usage_func")
    providers = current_app.config.get("PROVIDERS")

    cpu, mem = get_resource_usage()
    db_sizes = {}
    for db in ["users.db", "agent_memory_v3.db", "openbot_v3.log"]:
        try:
            size = os.path.getsize(os.path.join(base_dir, db)) / (1024 * 1024)
            db_sizes[db] = f"{size:.2f} MB"
        except:
            db_sizes[db] = "N/A"

    all_executions = []
    for user, history in tool_engine.execution_history.items():
        all_executions.extend(history)

    tool_usage = {}
    for exec in all_executions:
        tool = exec['tool']
        tool_usage[tool] = tool_usage.get(tool, 0) + 1

    memory_global = await memory_sql.memory_stats()

    return jsonify({
        "status": "success",
        "system": {
            "provider":  providers[active_provider_name]["label"],
            "model":     model,
            "base_dir":  base_dir,
            "resources": {"cpu": f"{cpu}%", "memory": f"{mem}MB"},
            "databases": db_sizes,
            "cache": {
                "tool_cache":   len(tool_engine.cache),
                "thread_pool":  thread_pool._max_workers,
                "process_pool": process_pool._max_workers
            }
        },
        "tools": {
            "total_executions": len(all_executions),
            "unique_users":     len(tool_engine.execution_history),
            "usage":            tool_usage,
            "available":        len(tool_registry.list_tools())
        },
        "memory": memory_global.get('stats', {}) if memory_global['status'] == 'success' else {}
    })
