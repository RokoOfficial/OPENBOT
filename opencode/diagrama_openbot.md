# Diagrama de Fluxo de Interação do OPENBOT

Este documento descreve o fluxo de interação do sistema OPENBOT, conforme ilustrado no diagrama fornecido. O sistema é projetado para responder a perguntas do usuário de forma eficiente e personalizada, utilizando um loop de agente, memória hierárquica (HGR), cache e um mecanismo de cálculo de importância.

## Usuário

A interação começa com uma pergunta do usuário, neste caso, Rudjery perguntando: "qual meu nome?". Esta é a entrada inicial para o sistema OPENBOT.

## OPENBOT - Loop do Agente (Nível 1)

O **Loop do Agente** é o núcleo do OPENBOT, responsável por processar a entrada do usuário e determinar a ação apropriada. Ele segue os seguintes passos:

*   **Pensa**: O agente analisa a pergunta e formula uma intenção, como "Preciso lembrar o nome".
*   **Usa ferramenta**: O agente invoca uma ferramenta, como `memory_recall("user_name")`, para buscar informações relevantes.
*   **Obtém**: A ferramenta retorna o resultado, por exemplo, "RUDJERY (importância 0.9)".
*   **Responde**: O agente formula uma resposta com base nas informações obtidas, como "Seu nome é RUDJERY!".

## Memória HGR (Nível 2)

A **Memória HGR (Hierarchical Graph-based Retrieval)** é responsável por armazenar e gerenciar informações de longo prazo. Quando o agente interage com a memória:

*   **Registra**: Eventos e interações são registrados, como "Perguntaram sobre o nome".
*   **Atualiza**: A importância das informações é atualizada com base no acesso, por exemplo, "Acesso #2, importância mantida".
*   **Guarda**: Detalhes como timestamp, contexto e resultado são armazenados para referência futura.

## Cache (Nível 3)

O **Cache** atua como uma camada de otimização para acelerar as respostas. Ele armazena resultados de consultas frequentes à memória:

*   **Cache da consulta à memória**: As respostas da memória são armazenadas temporariamente.
*   **TTL renovado por acesso**: O tempo de vida (TTL) do item em cache é renovado a cada acesso, garantindo que informações relevantes permaneçam acessíveis rapidamente.
*   **Próxima resposta será MAIS RÁPIDA**: A presença de um cache garante que interações repetidas sobre o mesmo tópico sejam processadas mais rapidamente.

## Importância (Nível 4)

O mecanismo de **Importância** avalia a relevância das informações para o usuário e para o sistema:

*   **"Nome foi acessado 2x hoje"**: O sistema rastreia a frequência de acesso a determinadas informações.
*   **"Rudjery pergunta sobre si mesmo"**: O contexto da pergunta também influencia a importância.
*   **"Importância pode SUBIR para 0.95"**: A importância de uma informação pode ser ajustada dinamicamente, tornando-a mais proeminente para futuras interações.

## Próxima Interação

O resultado da integração desses componentes é uma experiência de usuário aprimorada:

*   **Mais rápido (cache)**: Respostas mais rápidas devido ao armazenamento em cache.
*   **Mais preciso (memória)**: Respostas mais acuradas e contextualmente relevantes devido à memória HGR.
*   **Mais personalizado (importância)**: Interações mais personalizadas, pois o sistema compreende a relevância das informações para o usuário.
*   **Mais evoluído!**: O sistema aprende e se adapta continuamente, proporcionando uma experiência mais sofisticada ao longo do tempo.
