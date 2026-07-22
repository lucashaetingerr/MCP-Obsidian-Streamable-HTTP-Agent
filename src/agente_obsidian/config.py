"""Configuração do agente.

Tudo que normalmente muda de uma pessoa/uso pra outro fica aqui. As
credenciais e o endereço do MCP vêm de variáveis de ambiente (dá pra
sobrescrever num .env); o resto tem valor padrão mas pode ser editado
direto na dataclass abaixo, sem precisar mexer no resto do projeto.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


DEFAULT_SYSTEM_PROMPT = """\
Você é um assistente que ajuda a organizar, explorar e escrever notas \
no Obsidian do usuário. Você tem acesso ao vault dele via ferramentas \
(tools) — use-as sempre que a resposta depender de algo que está nas \
notas, em vez de chutar. Antes de criar ou sobrescrever uma nota, \
confirme com o usuário, a menos que ele já tenha pedido isso de forma \
explícita. Responda em markdown quando ajudar na leitura."""


@dataclass
class AgentConfig:
    name: str = "Nôta"
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    # modelo e parâmetros de geração
    model: str = "claude-sonnet-4-5"
    max_tokens: int = 2048
    temperature: float = 0.4

    # onde fica o servidor MCP do Obsidian (plugin tipo "MCP Tools",
    # "Local REST API + MCP bridge" etc). Ajuste a porta se for diferente.
    obsidian_mcp_url: str = os.environ.get(
        "OBSIDIAN_MCP_URL", "http://127.0.0.1:27124/mcp"
    )

    # None = libera todas as tools que o servidor expuser. Se preferir
    # um agente só de leitura, por exemplo, restrinja aqui.
    allowed_tools: list[str] | None = None

    # trava de segurança pra não deixar o agente ficar chamando tool
    # em loop indefinidamente numa resposta só
    max_tool_calls_per_turn: int = 6

    # log de debug mostrando qual tool foi chamada e com quais argumentos
    verbose_tool_calls: bool = True

    def anthropic_api_key(self) -> str:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY não encontrada no ambiente. "
                "Defina antes de rodar (ver .env.example)."
            )
        return key
