#!/usr/bin/env python3
"""
Sistema de Autenticação para OPENROKO
Recursos:
- Registro de usuários
- Login com JWT
- Hash seguro de senhas (bcrypt)
- Validação de tokens
- Rate limiting
"""

import os
import jwt
import bcrypt
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from functools import wraps
from quart import request, jsonify
import re

# ============================================================
# CONFIGURAÇÕES DE SEGURANÇA
# ============================================================

JWT_SECRET = os.environ.get("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Requisitos de senha
MIN_PASSWORD_LENGTH = 8
REQUIRE_UPPERCASE = True
REQUIRE_LOWERCASE = True
REQUIRE_DIGIT = True
REQUIRE_SPECIAL = False

# Rate limiting (tentativas de login)
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = 900  # 15 minutos


# ============================================================
# BANCO DE DADOS DE USUÁRIOS
# ============================================================

class UserDatabase:
    """Gerenciador de banco de dados de usuários"""
    
    def __init__(self, db_path: str = "users.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Inicializa o banco de dados"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabela de usuários
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at REAL NOT NULL,
                last_login REAL,
                is_active INTEGER DEFAULT 1,
                is_admin INTEGER DEFAULT 0,
                metadata TEXT
            )
        """)
        
        # Tabela de tentativas de login
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ip_address TEXT,
                timestamp REAL NOT NULL,
                success INTEGER NOT NULL
            )
        """)
        
        # Tabela de tokens revogados
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS revoked_tokens (
                token TEXT PRIMARY KEY,
                revoked_at REAL NOT NULL
            )
        """)
        
        # Índices
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_username 
            ON users(username)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_login_attempts 
            ON login_attempts(username, timestamp)
        """)
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        """Retorna conexão com o banco"""
        return sqlite3.connect(self.db_path)


# ============================================================
# VALIDAÇÃO DE SENHA
# ============================================================

class PasswordValidator:
    """Validador de requisitos de senha"""
    
    @staticmethod
    def validate(password: str) -> Tuple[bool, str]:
        """
        Valida senha contra requisitos de segurança
        Retorna (is_valid, error_message)
        """
        if len(password) < MIN_PASSWORD_LENGTH:
            return False, f"Senha deve ter no mínimo {MIN_PASSWORD_LENGTH} caracteres"
        
        if REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
            return False, "Senha deve conter pelo menos uma letra maiúscula"
        
        if REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
            return False, "Senha deve conter pelo menos uma letra minúscula"
        
        if REQUIRE_DIGIT and not re.search(r'\d', password):
            return False, "Senha deve conter pelo menos um número"
        
        if REQUIRE_SPECIAL and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False, "Senha deve conter pelo menos um caractere especial"
        
        return True, ""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Cria hash seguro da senha"""
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verifica se a senha corresponde ao hash"""
        return bcrypt.checkpw(
            password.encode('utf-8'),
            password_hash.encode('utf-8')
        )


# ============================================================
# VALIDAÇÃO DE EMAIL
# ============================================================

class EmailValidator:
    """Validador de email"""
    
    EMAIL_REGEX = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    
    @staticmethod
    def validate(email: str) -> Tuple[bool, str]:
        """Valida formato do email"""
        if not email or len(email) < 5:
            return False, "Email inválido"
        
        if not EmailValidator.EMAIL_REGEX.match(email):
            return False, "Formato de email inválido"
        
        return True, ""


# ============================================================
# GERENCIADOR DE AUTENTICAÇÃO
# ============================================================

class AuthManager:
    """Gerenciador principal de autenticação"""
    
    def __init__(self, db: UserDatabase):
        self.db = db
        self.password_validator = PasswordValidator()
        self.email_validator = EmailValidator()
    
    # ────────────────────────────────────────────────────
    # REGISTRO DE USUÁRIO
    # ────────────────────────────────────────────────────
    
    def register_user(
        self,
        username: str,
        email: str,
        password: str,
        metadata: Optional[Dict] = None
    ) -> Tuple[bool, str, Optional[Dict]]:
        """
        Registra novo usuário
        Retorna (success, message, user_data)
        """
        # Validar username
        if not username or len(username) < 3:
            return False, "Username deve ter no mínimo 3 caracteres", None
        
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            return False, "Username deve conter apenas letras, números e underscore", None
        
        # Validar email
        email_valid, email_error = self.email_validator.validate(email)
        if not email_valid:
            return False, email_error, None
        
        # Validar senha
        password_valid, password_error = self.password_validator.validate(password)
        if not password_valid:
            return False, password_error, None
        
        # Hash da senha
        password_hash = self.password_validator.hash_password(password)
        
        # Inserir no banco
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO users (username, email, password_hash, created_at, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (
                username,
                email.lower(),
                password_hash,
                time.time(),
                str(metadata) if metadata else None
            ))
            
            user_id = cursor.lastrowid
            conn.commit()
            
            return True, "Usuário registrado com sucesso", {
                "user_id": user_id,
                "username": username,
                "email": email.lower()
            }
        
        except sqlite3.IntegrityError as e:
            if "username" in str(e):
                return False, "Username já existe", None
            elif "email" in str(e):
                return False, "Email já cadastrado", None
            else:
                return False, f"Erro ao registrar: {str(e)}", None
        
        finally:
            conn.close()
    
    # ────────────────────────────────────────────────────
    # LOGIN
    # ────────────────────────────────────────────────────
    
    def login(
        self,
        username: str,
        password: str,
        ip_address: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Autentica usuário
        Retorna (success, message, jwt_token)
        """
        # Verificar rate limiting
        if self._is_locked_out(username):
            return False, "Muitas tentativas falhas. Tente novamente em 15 minutos", None
        
        # Buscar usuário
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, username, email, password_hash, is_active, is_admin
            FROM users
            WHERE username = ?
        """, (username,))
        
        user = cursor.fetchone()
        
        # Usuário não encontrado
        if not user:
            self._record_login_attempt(username, ip_address, False)
            conn.close()
            return False, "Credenciais inválidas", None
        
        user_id, username, email, password_hash, is_active, is_admin = user
        
        # Usuário inativo
        if not is_active:
            conn.close()
            return False, "Conta desativada", None
        
        # Verificar senha
        if not self.password_validator.verify_password(password, password_hash):
            self._record_login_attempt(username, ip_address, False)
            conn.close()
            return False, "Credenciais inválidas", None
        
        # Login bem-sucedido
        self._record_login_attempt(username, ip_address, True)
        
        # Atualizar último login
        cursor.execute("""
            UPDATE users
            SET last_login = ?
            WHERE id = ?
        """, (time.time(), user_id))
        conn.commit()
        conn.close()
        
        # Gerar JWT token
        token = self._generate_jwt_token({
            "user_id": user_id,
            "username": username,
            "email": email,
            "is_admin": bool(is_admin)
        })
        
        return True, "Login realizado com sucesso", token
    
    # ────────────────────────────────────────────────────
    # VALIDAÇÃO DE TOKEN
    # ────────────────────────────────────────────────────
    
    def validate_token(self, token: str) -> Tuple[bool, Optional[Dict]]:
        """
        Valida JWT token
        Retorna (is_valid, user_data)
        """
        # Verificar se token foi revogado
        if self._is_token_revoked(token):
            return False, None
        
        try:
            payload = jwt.decode(
                token,
                JWT_SECRET,
                algorithms=[JWT_ALGORITHM]
            )
            
            return True, payload
        
        except jwt.ExpiredSignatureError:
            return False, None
        except jwt.InvalidTokenError:
            return False, None
    
    def revoke_token(self, token: str):
        """Revoga um token (logout)"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR IGNORE INTO revoked_tokens (token, revoked_at)
            VALUES (?, ?)
        """, (token, time.time()))
        
        conn.commit()
        conn.close()
    
    # ────────────────────────────────────────────────────
    # MÉTODOS AUXILIARES
    # ────────────────────────────────────────────────────
    
    def _generate_jwt_token(self, user_data: Dict) -> str:
        """Gera JWT token"""
        payload = {
            **user_data,
            "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
            "iat": datetime.utcnow()
        }
        
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    def _record_login_attempt(
        self,
        username: str,
        ip_address: Optional[str],
        success: bool
    ):
        """Registra tentativa de login"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO login_attempts (username, ip_address, timestamp, success)
            VALUES (?, ?, ?, ?)
        """, (username, ip_address, time.time(), int(success)))
        
        conn.commit()
        conn.close()
    
    def _is_locked_out(self, username: str) -> bool:
        """Verifica se usuário está bloqueado por muitas tentativas"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cutoff_time = time.time() - LOCKOUT_DURATION
        
        cursor.execute("""
            SELECT COUNT(*)
            FROM login_attempts
            WHERE username = ?
              AND timestamp > ?
              AND success = 0
        """, (username, cutoff_time))
        
        failed_attempts = cursor.fetchone()[0]
        conn.close()
        
        return failed_attempts >= MAX_LOGIN_ATTEMPTS
    
    def _is_token_revoked(self, token: str) -> bool:
        """Verifica se token foi revogado"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*)
            FROM revoked_tokens
            WHERE token = ?
        """, (token,))
        
        count = cursor.fetchone()[0]
        conn.close()
        
        return count > 0


# ============================================================
# DECORADOR PARA ROTAS PROTEGIDAS
# ============================================================

def require_auth(admin_only: bool = False):
    """
    Decorador para proteger rotas que requerem autenticação
    
    Uso:
        @app.route("/api/protected")
        @require_auth()
        async def protected_route():
            user_data = request.user_data
            return jsonify({"message": f"Hello {user_data['username']}"})
    """
    def decorator(f):
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            # Extrair token do header
            auth_header = request.headers.get('Authorization')
            
            if not auth_header or not auth_header.startswith('Bearer '):
                return jsonify({
                    "error": "Token de autenticação não fornecido"
                }), 401
            
            token = auth_header.split(' ')[1]
            
            # Validar token
            from quart import current_app
            auth_manager = current_app.config.get('auth_manager')
            
            is_valid, user_data = auth_manager.validate_token(token)
            
            if not is_valid:
                return jsonify({
                    "error": "Token inválido ou expirado"
                }), 401
            
            # Verificar se requer admin
            if admin_only and not user_data.get('is_admin'):
                return jsonify({
                    "error": "Acesso negado: requer privilégios de admin"
                }), 403
            
            # Adicionar dados do usuário ao request
            request.user_data = user_data
            
            return await f(*args, **kwargs)
        
        return decorated_function
    return decorator


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def get_client_ip(request_obj) -> str:
    """Extrai IP do cliente do request"""
    if request_obj.headers.get('X-Forwarded-For'):
        return request_obj.headers.get('X-Forwarded-For').split(',')[0]
    return request_obj.remote_addr or 'unknown'


def cleanup_old_tokens(db: UserDatabase, days: int = 7):
    """Remove tokens revogados antigos"""
    cutoff = time.time() - (days * 24 * 3600)
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        DELETE FROM revoked_tokens
        WHERE revoked_at < ?
    """, (cutoff,))
    
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    return deleted
