#!/bin/bash

# ============================================================
# OPENROKO v2.0 - Script de Instalação
# ============================================================

set -e  # Parar em caso de erro

echo "╔════════════════════════════════════════════════════════════╗"
echo "║         OPENROKO v2.0 - Instalação e Configuração         ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================
# VERIFICAR PYTHON
# ============================================================

echo "🔍 Verificando Python..."

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 não encontrado. Por favor, instale Python 3.8 ou superior."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "✅ Python $PYTHON_VERSION encontrado"

# ============================================================
# CRIAR AMBIENTE VIRTUAL (OPCIONAL)
# ============================================================

echo ""
read -p "Deseja criar um ambiente virtual? (s/n): " CREATE_VENV

if [[ "$CREATE_VENV" == "s" ]] || [[ "$CREATE_VENV" == "S" ]]; then
    echo "📦 Criando ambiente virtual..."
    python3 -m venv venv
    
    echo "🔄 Ativando ambiente virtual..."
    source venv/bin/activate
    echo "✅ Ambiente virtual ativado"
fi

# ============================================================
# INSTALAR DEPENDÊNCIAS
# ============================================================

echo ""
echo "📥 Instalando dependências..."

# Lista de pacotes necessários
PACKAGES=(
    "quart"
    "hypercorn"
    "openai"
    "bcrypt"
    "pyjwt"
    "psutil"
)

# Verificar se está em Termux
if [[ -d "/data/data/com.termux" ]]; then
    echo "📱 Ambiente Termux detectado - usando --break-system-packages"
    PIP_FLAGS="--break-system-packages"
else
    PIP_FLAGS=""
fi

# Atualizar pip
python3 -m pip install --upgrade pip $PIP_FLAGS

# Instalar pacotes
for package in "${PACKAGES[@]}"; do
    echo "  Installing $package..."
    python3 -m pip install "$package" $PIP_FLAGS
done

echo "✅ Dependências instaladas com sucesso"

# ============================================================
# CONFIGURAR VARIÁVEIS DE AMBIENTE
# ============================================================

echo ""
echo "🔧 Configurando variáveis de ambiente..."

# Verificar se .env já existe
if [ -f ".env" ]; then
    echo "⚠️ Arquivo .env já existe."
    read -p "Deseja sobrescrever? (s/n): " OVERWRITE_ENV
    
    if [[ "$OVERWRITE_ENV" != "s" ]] && [[ "$OVERWRITE_ENV" != "S" ]]; then
        echo "Mantendo .env existente"
    else
        rm .env
    fi
fi

# Criar .env se não existir
if [ ! -f ".env" ]; then
    echo "Criando arquivo .env..."
    
    # OpenAI API Key
    read -p "Digite sua OPENAI_API_KEY: " OPENAI_KEY
    
    # JWT Secret
    echo "Gerando JWT_SECRET aleatório..."
    JWT_SECRET=$(openssl rand -hex 32 2>/dev/null || cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 64 | head -n 1)
    
    # Ambiente
    read -p "Ambiente (development/production) [development]: " ENVIRONMENT
    ENVIRONMENT=${ENVIRONMENT:-development}
    
    # Criar arquivo .env
    cat > .env << EOF
# OpenAI Configuration
OPENAI_API_KEY=$OPENAI_KEY

# JWT Configuration
JWT_SECRET=$JWT_SECRET

# Environment
OPENROKO_ENV=$ENVIRONMENT

# Server Configuration
HOST=0.0.0.0
PORT=5000
DEBUG=true
EOF
    
    echo "✅ Arquivo .env criado"
fi

# ============================================================
# VERIFICAR ARQUIVOS NECESSÁRIOS
# ============================================================

echo ""
echo "📄 Verificando arquivos do projeto..."

REQUIRED_FILES=(
    "OPENBOT_TELEGRAM_V2.py"
    "HGR.py"
    "auth_system.py"
    "config.py"
)

MISSING_FILES=()

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✅ $file"
    else
        echo "  ❌ $file (faltando)"
        MISSING_FILES+=("$file")
    fi
done

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    echo ""
    echo "⚠️ Arquivos faltando: ${MISSING_FILES[*]}"
    echo "Por favor, certifique-se de que todos os arquivos estão no diretório."
    exit 1
fi

# ============================================================
# CRIAR DIRETÓRIOS NECESSÁRIOS
# ============================================================

echo ""
echo "📁 Criando diretórios..."

mkdir -p logs
mkdir -p backups

echo "✅ Diretórios criados"

# ============================================================
# TESTAR CONFIGURAÇÃO
# ============================================================

echo ""
echo "🧪 Testando configuração..."

python3 << EOF
import sys
sys.path.insert(0, '.')

try:
    from config import load_config_from_env
    
    config = load_config_from_env()
    is_valid, errors = config.validate()
    
    if is_valid:
        print("✅ Configuração válida!")
        config.print_summary()
        sys.exit(0)
    else:
        print("❌ Erros na configuração:")
        for error in errors:
            print(f"  • {error}")
        sys.exit(1)
except Exception as e:
    print(f"❌ Erro ao testar configuração: {e}")
    sys.exit(1)
EOF

if [ $? -ne 0 ]; then
    echo ""
    echo "⚠️ Falha na validação da configuração"
    exit 1
fi

# ============================================================
# CRIAR SCRIPT DE INICIALIZAÇÃO
# ============================================================

echo ""
echo "📝 Criando script de inicialização..."

cat > start.sh << 'EOF'
#!/bin/bash

# Carregar variáveis de ambiente
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Ativar ambiente virtual se existir
if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "🚀 Iniciando OPENROKO v2.0..."
python3 OPENBOT_TELEGRAM_V2.py
EOF

chmod +x start.sh

echo "✅ Script de inicialização criado (start.sh)"

# ============================================================
# CRIAR SCRIPT DE BACKUP
# ============================================================

echo ""
echo "💾 Criando script de backup..."

cat > backup.sh << 'EOF'
#!/bin/bash

BACKUP_DIR="backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.tar.gz"

echo "📦 Criando backup em $BACKUP_FILE..."

tar -czf "$BACKUP_FILE" \
    users.db \
    agent_memory.db \
    .env \
    agent_execution.log \
    2>/dev/null || true

if [ -f "$BACKUP_FILE" ]; then
    echo "✅ Backup criado com sucesso: $BACKUP_FILE"
    
    # Manter apenas os 10 backups mais recentes
    ls -t $BACKUP_DIR/backup_*.tar.gz | tail -n +11 | xargs -r rm
    echo "🗑️ Backups antigos removidos (mantendo 10 mais recentes)"
else
    echo "❌ Erro ao criar backup"
    exit 1
fi
EOF

chmod +x backup.sh

echo "✅ Script de backup criado (backup.sh)"

# ============================================================
# RESUMO FINAL
# ============================================================

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                  ✅ INSTALAÇÃO CONCLUÍDA                   ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "📚 Próximos passos:"
echo ""
echo "1. Iniciar o servidor:"
echo "   ./start.sh"
echo ""
echo "2. Testar a API:"
echo "   curl http://localhost:5000/"
echo ""
echo "3. Criar primeiro usuário:"
echo "   curl -X POST http://localhost:5000/api/auth/register \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"username\":\"admin\",\"email\":\"admin@example.com\",\"password\":\"Admin123!\"}'"
echo ""
echo "4. Fazer login:"
echo "   curl -X POST http://localhost:5000/api/auth/login \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"username\":\"admin\",\"password\":\"Admin123!\"}'"
echo ""
echo "📖 Documentação completa: API_DOCUMENTATION.md"
echo ""
echo "💾 Fazer backup:"
echo "   ./backup.sh"
echo ""
echo "🌟 Bom uso do OPENROKO v2.0!"
echo ""
