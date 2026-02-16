# 🤖 OpenBot v3.0 - Arquitetura Plug & Play com Tool Use

Bem-vindo ao **OpenBot v3.0**, uma plataforma de inteligência artificial autônoma e modular, projetada para ser o "canivete suíço" da automação e processamento de dados. Este projeto representa uma evolução significativa na integração entre Modelos de Linguagem de Grande Escala (LLMs) e a execução de ferramentas em tempo real.

> **Nota de Crédito:** Este projeto é uma evolução baseada no conceito original do **OpenBot Project**. Esta versão v3.0 foi aprimorada e expandida por **RokoOfficial**, introduzindo uma arquitetura de memória de três níveis e um sistema de ferramentas expandido.

---

## 🚀 Visão Geral

O OpenBot não é apenas um chatbot; é um **Agente Autônomo** capaz de interagir com o sistema operacional, executar código, gerenciar bancos de dados e realizar operações de rede complexas. Utilizando a API do **GROQ** (com modelos Llama-3.1), o OpenBot alcança uma latência extremamente baixa, permitindo respostas e execuções quase instantâneas.

### 🧠 Arquitetura de Memória HGR (3 Níveis)
Diferente de sistemas convencionais, o OpenBot utiliza o sistema **HGR Memory**, que organiza o conhecimento em três camadas:
1.  **Memória de Curto Prazo:** Mantém o contexto imediato da conversa para respostas rápidas.
2.  **Memória de Trabalho:** Processa informações relevantes para a tarefa atual.
3.  **Memória de Longo Prazo:** Armazena fatos, preferências e aprendizados em um banco de dados SQLite persistente, permitindo que o bot "lembre" de interações passadas entre sessões.

---

## 🛠️ O Arsenal de Ferramentas (40 Ferramentas)

O OpenBot vem equipado com um registro central de ferramentas divididas em categorias estratégicas:

| Categoria | Descrição | Exemplos de Ferramentas |
| :--- | :--- | :--- |
| **Python** | Execução e depuração de código em tempo real. | `python_execute`, `python_debug`, `python_inspect` |
| **Shell** | Interação direta com o sistema operacional. | `shell_execute`, `shell_script`, `system_status` |
| **Network** | Ferramentas de rede e comunicação. | `http_request`, `port_scan`, `dns_lookup` |
| **Filesystem** | Manipulação avançada de arquivos e diretórios. | `file_write`, `file_read`, `directory_map` |
| **Data** | Processamento de dados e SQL. | `sql_query`, `json_parse`, `csv_analyze` |
| **Crypto** | Operações de segurança e criptografia. | `hash_generate`, `encrypt_data`, `token_verify` |

---

## 🔐 Segurança e Autenticação

O sistema conta com uma camada de segurança robusta baseada em **JWT (JSON Web Tokens)**:
-   **Banco de Dados de Usuários:** Gerenciamento persistente de credenciais.
-   **Middleware de Autenticação:** Proteção de rotas API e controle de acesso.
-   **Isolamento de Processos:** Ferramentas perigosas são monitoradas e podem ser restritas.

---

## 📂 Estrutura do Projeto

A organização do repositório segue padrões modernos de modularidade:

```text
OPENBOT/
├── BOT/                # Núcleo do Agente
│   ├── OPENBOT.py      # Script principal e API Quart
│   ├── HGR.py          # Motor de Memória Avançada
│   ├── auth_system.py  # Sistema de Autenticação JWT
│   ├── config.py       # Configurações globais
│   └── install.sh      # Script de instalação automatizada
├── doc/                # Documentação Técnica Detalhada
├── LICENSE             # Licença MIT
└── README.md           # Esta apresentação
```

---

## 🛠️ Instalação Rápida

Para implantar o OpenBot em seu ambiente Linux, utilize o script de instalação automatizada:

```bash
cd BOT
chmod +x install.sh
./install.sh
```

### Pré-requisitos
- Python 3.10+
- Chave de API do GROQ (`GROQ_API_KEY`)
- Dependências listadas no `install.sh`

---

## 📄 Licença

Este projeto está licenciado sob a **Licença MIT**. Sinta-se à vontade para usar, modificar e distribuir, desde que mantenha os créditos originais ao **OpenBot Project** e as contribuições de **RokoOfficial**.

---
*Desenvolvido com foco em autonomia, velocidade e inteligência.*
