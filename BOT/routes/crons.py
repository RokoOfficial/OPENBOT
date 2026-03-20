import logging
from quart import Blueprint, request, jsonify, current_app
from auth_system import require_auth

crons_bp = Blueprint('crons', __name__)

def _job_to_dict(job):
    """Helper para converter objeto Job em dict JSON-serializável"""
    return {
        "id":          job.id,
        "name":        job.name,
        "description": job.description,
        "schedule":    job.schedule,
        "task_type":   job.task_type,
        "task":        job.task,
        "status":      job.status,
        "last_run":    job.last_run,
        "next_run":    job.next_run,
        "created_at":  job.created_at
    }

@crons_bp.route("/list", methods=["GET"])
@require_auth()
async def crons_list():
    """Lista os cron jobs do utilizador"""
    memory_agent = current_app.config.get("memory_agent")
    user_data = request.user_data
    uid       = user_data["username"]
    status    = request.args.get("status", "").strip() or None
    jobs      = memory_agent.crons.list_jobs(uid, status=status)
    return jsonify({"status": "success", "total": len(jobs), "jobs": [_job_to_dict(j) for j in jobs]})


@crons_bp.route("/create", methods=["POST"])
@require_auth()
async def crons_create():
    """Cria um novo cron job"""
    memory_agent = current_app.config.get("memory_agent")
    user_data = request.user_data
    uid       = user_data["username"]
    data      = await request.get_json()

    name      = (data.get("name") or "").strip()
    desc      = (data.get("description") or "").strip()
    schedule  = (data.get("schedule") or "").strip()
    task      = (data.get("task") or "").strip()
    task_type = (data.get("task_type") or "agent").strip()

    if not name:
        return jsonify({"error": "Campo 'name' obrigatório"}), 400
    if not schedule:
        return jsonify({"error": "Campo 'schedule' obrigatório"}), 400
    if not task:
        return jsonify({"error": "Campo 'task' obrigatório"}), 400
    if task_type not in ("agent", "shell", "http"):
        task_type = "agent"

    job = memory_agent.crons.create(uid, name, desc, schedule, task_type, task)
    logging.info(f"Cron criado: {name} ({schedule}) por {uid}")
    return jsonify({
        "status":   "success",
        "id":       job.id,
        "next_run": memory_agent.crons.format_next_run(job)
    })


@crons_bp.route("/<int:job_id>/run", methods=["POST"])
@require_auth()
async def crons_run_now(job_id):
    """Executa um cron job imediatamente via HGR CronManager"""
    memory_agent = current_app.config.get("memory_agent")
    user_data = request.user_data
    uid       = user_data["username"]
    result    = await memory_agent.crons.run_now(job_id, uid)
    if "error" in result:
        return jsonify({"error": result["error"]}), 404
    return jsonify({
        "status":      "success",
        "last_output": result.get("last_output", ""),
    })


@crons_bp.route("/<int:job_id>/toggle", methods=["PATCH"])
@require_auth()
async def crons_toggle(job_id):
    """Pausa ou ativa um cron job"""
    memory_agent = current_app.config.get("memory_agent")
    user_data = request.user_data
    uid       = user_data["username"]
    job       = memory_agent.crons.toggle(job_id, uid)
    if job is None:
        return jsonify({"error": "Job não encontrado"}), 404
    return jsonify({"status": "success", "new_status": job.status})


@crons_bp.route("/<int:job_id>", methods=["DELETE"])
@require_auth()
async def crons_delete(job_id):
    """Apaga um cron job"""
    memory_agent = current_app.config.get("memory_agent")
    user_data = request.user_data
    uid       = user_data["username"]
    ok        = memory_agent.crons.delete(job_id, uid)
    if not ok:
        return jsonify({"error": "Job não encontrado"}), 404
    return jsonify({"status": "success"})


@crons_bp.route("/<int:job_id>/logs", methods=["GET"])
@require_auth()
async def crons_logs(job_id):
    """Retorna logs de execução de um cron job"""
    memory_agent = current_app.config.get("memory_agent")
    user_data = request.user_data
    uid       = user_data["username"]
    limit     = int(request.args.get("limit", 10))
    # Verifica ownership
    job = memory_agent.crons.get(job_id)
    if not job or job.user_id != uid:
        return jsonify({"error": "Job não encontrado"}), 404
    logs = memory_agent.crons.get_logs(job_id, limit=limit)
    return jsonify({"status": "success", "total": len(logs), "logs": logs})
