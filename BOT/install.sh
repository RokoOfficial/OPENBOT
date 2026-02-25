#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
# OPENBOT v4.0 — Script de Instalação
# Compatível com: Termux (Android) · Ubuntu/Debian · macOS
# ══════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Cores ──────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[AVISO]${NC} $*"; }
error()   { echo -e "${RED}[ERRO]${NC}  $*"; exit 1; }

# ── Cabeçalho ─────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║        OPENBOT v4.0 — Instalação                ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── Detecção de ambiente ───────────────────────────────────────
detect_env() {
    if [ -d "/data/data/com.termux" ]; then
        echo "termux"
    elif command -v apt-get &>/dev/null; then
        echo "debian"
    elif command -v brew &>/dev/null; then
        echo "macos"
    else
        echo "generic"
    fi
}

ENV=$(detect_env)
info "Ambiente detectado: $ENV"

# ── Verificar Python ──────────────────────────────────────────
PY=$(command -v python3 || command -v python || echo "")
[ -z "$PY" ] && error "Python 3 não encontrado. Instale-o antes de continuar."

PY_VERSION=$($PY --version 2>&1 | awk '{print $2}')
info "Python: $PY_VERSION ($PY)"

# ── Instalar dependências do sistema ──────────────────────────
install_system_deps() {
    case "$ENV" in
        termux)
            info "Instalando dependências no Termux..."
            pkg update -y -q
            pkg install -y -q python python-pip openssl libffi
            ;;
        debian)
            info "Instalando dependências (apt)..."
            sudo apt-get update -qq
            sudo apt-get install -y -qq python3-pip python3-venv libssl-dev libffi-dev
            ;;
        macos)
            info "Instalando dependências (brew)..."
            brew install python openssl 2>/dev/null || true
            ;;
        *)
            warn "Ambiente não reconhecido. Pulando instalação de dependências do sistema."
            ;;
    esac
}

install_system_deps

# ── Criar e ativar ambiente virtual (exceto Termux) ───────────
VENV_DIR="venv"
if [ "$ENV" != "termux" ]; then
    if [ ! -d "$VENV_DIR" ]; then
        info "Criando ambiente virtual..."
        $PY -m venv "$VENV_DIR"
        success "Ambiente virtual criado: $VENV_DIR"
    else
        info "Ambiente virtual já existe: $VENV_DIR"
    fi
    source "$VENV_DIR/bin/activate"
    PY="python"
fi

# ── Instalar dependências Python ──────────────────────────────
info "Instalando dependências Python..."

$PY -m pip install --upgrade pip -q

# Dependências principais
PACKAGES=(
    "quart>=0.19.4"
    "quart-cors>=0.6.0"
    "hypercorn>=0.16.0"
    "openai==0.28.1"          # Compatível com todos os providers (api_base)
    "PyJWT>=2.8.0"
    "bcrypt>=4.1.2"
    "aiohttp>=3.9.0"
    "psutil>=5.9.0"
    "requests>=2.31.0"
    "python-dotenv>=1.0.0"
)

# Dependências opcionais (não bloqueiam instalação)
OPTIONAL_PACKAGES=(
    "jmespath"
    "autopep8"
)

for pkg in "${PACKAGES[@]}"; do
    $PY -m pip install "$pkg" -q && success "$pkg" || error "Falha ao instalar $pkg"
done

for pkg in "${OPTIONAL_PACKAGES[@]}"; do
    $PY -m pip install "$pkg" -q && success "$pkg (opcional)" || warn "$pkg não instalado (opcional)"
done

# ── Criar arquivo .env ────────────────────────────────────────
setup_env() {
    if [ -f ".env" ]; then
        warn ".env já existe."
        read -r -p "Deseja recriar? (s/N): " RECREATE
        [[ "${RECREATE,,}" != "s" ]] && return
    fi

    echo ""
    info "Configurando variáveis de ambiente..."

    # Provider
    echo ""
    echo "Providers disponíveis:"
    echo "  1) deepseek  (recomendado — custo baixo)"
    echo "  2) groq       (gratuito — muito rápido)"
    echo "  3) openai     (GPT-4)"
    echo "  4) anthropic  (Claude)"
    read -r -p "Provider [1-4, padrão=1]: " PROV_CHOICE

    case "$PROV_CHOICE" in
        2) PROVIDER="groq";      KEY_VAR="GROQ_API_KEY" ;;
        3) PROVIDER="openai";    KEY_VAR="OPENAI_API_KEY" ;;
        4) PROVIDER="anthropic"; KEY_VAR="ANTHROPIC_API_KEY" ;;
        *) PROVIDER="deepseek";  KEY_VAR="DEEPSEEK_API_KEY" ;;
    esac

    read -r -p "Digite sua $KEY_VAR: " API_KEY
    [ -z "$API_KEY" ] && warn "API Key vazia — configure depois no .env"

    # JWT Secret
    JWT_SECRET=$(openssl rand -hex 32 2>/dev/null || $PY -c "import secrets; print(secrets.token_hex(32))")

    # Ambiente
    read -r -p "Ambiente (development/production) [development]: " APP_ENV
    APP_ENV="${APP_ENV:-development}"

    # Diretório base
    DEFAULT_BASE="$HOME/openbot_workspace"
    read -r -p "Diretório de trabalho [$DEFAULT_BASE]: " BASE_DIR
    BASE_DIR="${BASE_DIR:-$DEFAULT_BASE}"

    cat > .env << EOF
# ── Provider de IA ────────────────────────
OPENBOT_PROVIDER=$PROVIDER
$KEY_VAR=$API_KEY

# ── Segurança ─────────────────────────────
JWT_SECRET=$JWT_SECRET

# ── Ambiente ──────────────────────────────
OPENBOT_ENV=$APP_ENV
OPENBOT_DEBUG=$([ "$APP_ENV" = "development" ] && echo "true" || echo "false")

# ── Servidor ──────────────────────────────
HOST=0.0.0.0
PORT=5000

# ── Diretório base ────────────────────────
OPENBOT_BASE_DIR=$BASE_DIR

# ── CORS (produção: separe origens com vírgula) ────────────────
# CORS_ORIGINS=https://meusite.com,https://app.meusite.com
CORS_ORIGINS=*
EOF

    success ".env criado com sucesso"
}

setup_env

# ── Verificar arquivos do projeto ────────────────────────────
echo ""
info "Verificando arquivos do projeto..."
REQUIRED=("OPENBOT.py" "HGR.py" "auth_system.py" "config.py")
MISSING=()

for f in "${REQUIRED[@]}"; do
    if [ -f "$f" ]; then
        success "$f"
    else
        warn "$f não encontrado"
        MISSING+=("$f")
    fi
done

[ ${#MISSING[@]} -gt 0 ] && error "Arquivos faltando: ${MISSING[*]}"

# ── Criar diretórios ──────────────────────────────────────────
echo ""
info "Criando estrutura de diretórios..."

BASE_DIR_VALUE=$(grep "OPENBOT_BASE_DIR" .env | cut -d= -f2)
BASE_DIR_VALUE="${BASE_DIR_VALUE:-$HOME/openbot_workspace}"

for dir in "$BASE_DIR_VALUE" "$BASE_DIR_VALUE/exports" "$BASE_DIR_VALUE/logs" "$BASE_DIR_VALUE/backups"; do
    mkdir -p "$dir" && success "$dir"
done

# ── Teste de configuração ─────────────────────────────────────
echo ""
info "Testando configuração..."

$PY - << 'PYEOF'
import sys
sys.path.insert(0, '.')
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import load_config_from_env
cfg = load_config_from_env()
valid, errors = cfg.validate()
cfg.print_summary()

if valid:
    print("\n✅ Configuração válida!")
else:
    print("\n⚠️  Avisos:")
    for e in errors:
        print(f"  • {e}")
PYEOF

# ── Resumo final ──────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
success "Instalação concluída!"
echo ""
echo "Para iniciar o servidor:"
if [ "$ENV" != "termux" ]; then
    echo "  source venv/bin/activate"
fi
echo "  python OPENBOT.py"
echo ""
echo "Com CORS habilitado:"
echo "  python OPENBOT_CORS.py"
echo ""
echo "Acessar a API:"
echo "  http://localhost:5000"
echo "═══════════════════════════════════════════════════"
