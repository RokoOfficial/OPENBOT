import os
import sqlite3
import uuid
import bcrypt
import secrets
from functools import wraps
from typing import Optional, Dict, Any

from quart import Quart, request, jsonify

from HVM import Engine

app = Quart(__name__)
DB_PATH = os.getenv("DB_PATH", "hvm_auth.sqlite3")
FS_ROOT = os.path.abspath(os.getenv("FS_ROOT", os.path.join(os.path.expanduser("~"), "openbot_workspace")))
os.makedirs(FS_ROOT, exist_ok=True)


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id TEXT PRIMARY KEY,
                name TEXT,
                email TEXT UNIQUE,
                password_hash TEXT,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                token TEXT PRIMARY KEY,
                client_id TEXT,
                scope TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


init_db()


def resolve_fs_path(path: Optional[str] = None) -> str:
    if not path:
        return FS_ROOT
    candidate = path if isinstance(path, str) else str(path)
    full = os.path.abspath(candidate if os.path.isabs(candidate) else os.path.join(FS_ROOT, candidate))
    if os.path.commonpath([FS_ROOT, full]) != FS_ROOT:
        raise ValueError("fs: path fora do escopo permitido")
    return full


def db():
    return sqlite3.connect(DB_PATH)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(client_id: str, scope: str = "run,tools") -> str:
    token = "hvm_" + secrets.token_hex(16)
    with db() as conn:
        conn.execute("INSERT INTO tokens (token, client_id, scope) VALUES (?, ?, ?)", (token, client_id, scope))
    return token


def validate_token(token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    with db() as conn:
        cur = conn.execute(
            """
            SELECT c.id, c.name, c.email, t.scope
            FROM tokens t
            JOIN clients c ON c.id=t.client_id
            WHERE t.token=?
            """,
            (token,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "name": row[1], "email": row[2], "scope": row[3].split(",")}


def extract_token(req) -> Optional[str]:
    h = req.headers.get("Authorization", "")
    if h.startswith("Bearer "):
        return h.split(" ", 1)[1]
    return None


def require_auth(scope: Optional[str] = None):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            token = extract_token(request)
            client = validate_token(token)
            if not client:
                return jsonify({"error": "unauthorized"}), 401
            if scope and scope not in client["scope"]:
                return jsonify({"error": "forbidden"}), 403
            request.client = client
            return await fn(*args, **kwargs)

        return wrapper

    return decorator


@app.post("/auth/register")
async def register():
    data = await request.get_json(force=True)
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    if not all([name, email, password]):
        return jsonify({"error": "faltam campos"}), 400

    with db() as conn:
        try:
            conn.execute(
                "INSERT INTO clients (id, name, email, password_hash) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), name, email, hash_password(password)),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "email já registrado"}), 409
    return jsonify({"status": "ok"})


@app.post("/auth/login")
async def login():
    data = await request.get_json(force=True)
    email = data.get("email")
    password = data.get("password")
    with db() as conn:
        cur = conn.execute("SELECT id, password_hash FROM clients WHERE email=? AND active=1", (email,))
        row = cur.fetchone()
    if not row or not verify_password(password, row[1]):
        return jsonify({"error": "credenciais inválidas"}), 401
    token = create_token(row[0])
    return jsonify({"status": "ok", "token": token, "scopes": ["run", "tools"]})


@app.get("/auth/me")
@require_auth()
async def me():
    return jsonify(request.client)


@app.post("/auth/logout")
@require_auth()
async def logout():
    token = extract_token(request)
    with db() as conn:
        conn.execute("DELETE FROM tokens WHERE token=?", (token,))
    return jsonify({"status": "revogado"})


engine = Engine()
last_exec: Dict[str, Any] = {}


def response_from_ctx(ctx, result):
    global last_exec
    last_exec = {"vars": ctx.vars, "logs": ctx.logs, "metrics": ctx.metrics.asdict(), "result": result}
    return jsonify(last_exec)


@app.post("/hvm/run/code")
@require_auth("run")
async def run_code():
    data = await request.get_json(force=True)
    code = data.get("code", "")
    vars_in = data.get("initial_vars")
    ctx, result = engine.run_code(code, vars_in)
    return response_from_ctx(ctx, result)


@app.post("/hvm/run/batch")
@require_auth("run")
async def run_batch():
    data = await request.get_json(force=True)
    codes = data.get("codes", [])
    results = []
    for code in codes:
        ctx, res = engine.run_code(code)
        results.append({"result": res, "vars": ctx.vars, "logs": ctx.logs, "metrics": ctx.metrics.asdict()})
    return jsonify({"count": len(results), "items": results})


@app.get("/hvm/status")
@require_auth()
async def status():
    return jsonify({"version": "2.1.0-py", "tools_count": len(engine.vm.tools), "parallel_workers": engine.flux.max_workers})


@app.get("/hvm/last")
@require_auth()
async def last():
    return jsonify(last_exec or {"status": "sem execuções"})


@app.get("/fs/list")
@require_auth()
async def fs_list():
    path = request.args.get("path")
    try:
        full = resolve_fs_path(path)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not os.path.exists(full):
        return jsonify({"error": "path não encontrado"}), 404
    items = []
    for name in sorted(os.listdir(full)):
        entry_path = os.path.join(full, name)
        kind = "folder" if os.path.isdir(entry_path) else "file"
        items.append({"name": name, "type": kind, "path": entry_path, "rel_path": os.path.relpath(entry_path, FS_ROOT)})
    return jsonify({"path": full, "items": items})


@app.post("/fs/mkdir")
@require_auth("run")
async def fs_mkdir():
    payload = await request.get_json(force=True) or {}
    path = payload.get("path")
    if not path:
        return jsonify({"error": "path é obrigatório"}), 400
    try:
        full = resolve_fs_path(path)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    os.makedirs(full, exist_ok=True)
    return jsonify({"status": "ok", "path": full})


@app.get("/hvm/tools")
@require_auth("tools")
async def list_tools():
    return jsonify({"tools": sorted(engine.vm.tools.keys())})


@app.delete("/hvm/tools/<name>")
@require_auth("tools")
async def delete_tool(name: str):
    if name not in engine.vm.tools:
        return jsonify({"error": "tool não existe"}), 404
    del engine.vm.tools[name]
    return jsonify({"status": "deleted", "tool": name})


if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", 7777)), debug=os.getenv("DEBUG", "false").lower() == "true")
