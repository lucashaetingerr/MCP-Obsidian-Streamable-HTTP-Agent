# agente-obsidian

Agente de chat (Claude) com acesso direto ao seu vault do Obsidian via
MCP, usando o transporte streamable HTTP.

## Requisitos

- Python 3.10+
- Chave de API da Anthropic
- Obsidian rodando com um plugin que exponha um servidor MCP em HTTP
  (ex: "MCP Tools"). O plugin mostra a URL — algo como
  `http://127.0.0.1:27124/mcp`.

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate      # windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env           # e preenche a API key
```

## Rodando

```bash
export $(cat .env | xargs)     # ou exporta as variáveis manualmente
python -m agente_obsidian
```

(se instalou com `pip install -e .`, também dá pra rodar só `agente-obsidian`)

## Estrutura

```
src/agente_obsidian/
├── config.py           # AgentConfig — o que costuma mudar por uso
├── obsidian_client.py  # conexão MCP + conversão de tools
├── agent.py            # loop de conversa / uso de tools
├── cli.py              # chat de terminal
└── __main__.py
```

## Customizando o agente

A maior parte do que dá pra ajustar tá em `config.py`, na classe
`AgentConfig`:

- `name` / `system_prompt` — quem o agente é, como ele responde
- `model`, `max_tokens`, `temperature`
- `obsidian_mcp_url` — endereço do servidor MCP (também pode vir de
  `OBSIDIAN_MCP_URL` no ambiente)
- `allowed_tools` — restringe quais tools do Obsidian ele pode chamar
  (`None` libera todas)
- `verbose_tool_calls` — loga no terminal cada tool chamada

Pra ter mais de um "perfil" de agente, basta instanciar `AgentConfig`
mais de uma vez com valores diferentes (dá pra fazer isso num script à
parte, sem tocar no resto do pacote).
