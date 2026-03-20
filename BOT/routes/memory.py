import json
import logging
from quart import Blueprint, request, jsonify, current_app
from auth_system import require_auth

memory_bp = Blueprint('memory', __name__)
logger = logging.getLogger(__name__)

@memory_bp.route("/list", methods=["GET"])
@require_auth()
async def memory_list():
    """Lista memórias do utilizador — funde memory_sql (memories) + HGR facts (auto-extraídos)"""
    memory_sql = current_app.config.get("memory_sql")
    memory_agent = current_app.config.get("memory_agent")
    
    user_data = request.user_data
    uid       = user_data["username"]

    search      = request.args.get("search", "").strip()
    category    = request.args.get("category", "").strip()
    limit       = int(request.args.get("limit", 200))
    min_imp     = float(request.args.get("min_importance", 0))

    # ── FONTE 1: memory_sql (memories manuais/LLM tools — agent_memory_v3.db) ──
    if search:
        result   = await memory_sql.memory_search(uid, search, min_importance=min_imp)
        sql_mems = result.get("results", [])
    else:
        result   = await memory_sql.memory_recall(
            uid, category=category or None,
            min_importance=min_imp, limit=limit
        )
        sql_mems = result.get("memories", [])

    # ── FONTE 2: HGR facts (auto-extraídos após cada conversa — agent_memory.db) ──
    try:
        hgr_facts_raw = memory_agent.facts.recall(
            uid,
            category=category or None,
            limit=limit,
            min_importance=min_imp
        )
        hgr_mems = []
        for f in hgr_facts_raw:
            hgr_mems.append({
                "id":           f.get("id", 0),
                "user_id":      uid,
                "key":          f.get("key", ""),
                "value":        f.get("value", ""),
                "importance":   f.get("importance", 0.5),
                "category":     f.get("category", "auto_extracted"),
                "tags":         json.loads(f["tags"]) if isinstance(f.get("tags"), str) else (f.get("tags") or []),
                "access_count": f.get("access_count", 0),
                "created_at":   f.get("created_at", 0),
                "source":       "hgr"
            })
        if search:
            term = search.lower()
            hgr_mems = [m for m in hgr_mems
                        if term in m["key"].lower() or term in str(m["value"]).lower()]
    except Exception as e:
        logger.warning(f"[memory/list] HGR facts erro (nao fatal): {e}")
        hgr_mems = []

    # ── FUSÃO: evita duplicados pela chave ──────────────────────────────────────
    seen_keys = set()
    memories  = []
    for m in sql_mems:
        k = str(m.get("key", ""))
        seen_keys.add(k)
        memories.append(m)
    for m in hgr_mems:
        k = str(m.get("key", ""))
        if k not in seen_keys:
            seen_keys.add(k)
            memories.append(m)

    # Ordena por importância desc e aplica limit
    memories.sort(key=lambda x: float(x.get("importance", 0)), reverse=True)
    if limit:
        memories = memories[:limit]

    # ── Normaliza created_at para timestamp Unix (frontend: new Date(x*1000)) ──
    from datetime import datetime as _dt
    for m in memories:
        ca = m.get("created_at")
        if isinstance(ca, str):
            try:    m["created_at"] = int(_dt.fromisoformat(ca).timestamp())
            except: m["created_at"] = 0
        elif ca is None:
            m["created_at"] = 0

    # ── Stats combinadas ────────────────────────────────────────────────────────
    stats_result = await memory_sql.memory_stats(uid)
    stats        = stats_result.get("stats", {}) if stats_result.get("status") == "success" else {}
    hgr_stats    = memory_agent.facts.stats(uid)

    total_cats = max(
        stats.get("unique_categories", 0),
        hgr_stats.get("unique_categories", 0)
    )
    avg_imp_sql = stats.get("avg_importance") or 0
    avg_imp_hgr = hgr_stats.get("avg_importance") or 0
    avg_imp = round((avg_imp_sql + avg_imp_hgr) / 2 if avg_imp_sql and avg_imp_hgr
                    else avg_imp_sql or avg_imp_hgr, 2)

    return jsonify({
        "status":   "success",
        "count":    len(memories),
        "memories": memories,
        "stats": {
            "unique_categories": total_cats,
            "avg_importance":    avg_imp,
            "total_accesses":    stats.get("total_accesses", 0)
        }
    })


@memory_bp.route("/delete/<int:memory_id>", methods=["DELETE"])
@require_auth()
async def memory_delete_one(memory_id):
    """Apaga uma memória específica pelo ID"""
    memory_sql = current_app.config.get("memory_sql")
    user_data = request.user_data
    uid       = user_data["username"]
    result    = await memory_sql.memory_delete(uid, memory_id=memory_id)
    if result.get("status") == "success":
        return jsonify({"status": "success", "deleted": memory_id})
    return jsonify({"error": result.get("error", "Não encontrado")}), 404


@memory_bp.route("/delete-all", methods=["DELETE"])
@require_auth()
async def memory_delete_all():
    """Apaga todas as memórias do utilizador"""
    memory_sql = current_app.config.get("memory_sql")
    user_data = request.user_data
    uid       = user_data["username"]
    result    = await memory_sql.memory_delete(uid, delete_all=True)
    return jsonify({"status": "success", "message": "Todas as memórias apagadas."})
