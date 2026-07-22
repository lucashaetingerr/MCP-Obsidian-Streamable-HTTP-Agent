"""Ponte com o servidor MCP do Obsidian.

Isola tudo que é específico do protocolo MCP num lugar só, pra o resto
do código (agent.py) não precisar saber como uma tool_result é montada
ou como o transporte streamable HTTP funciona por baixo.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


class ObsidianMCPClient:
    """Sessão ativa com o servidor MCP, já com as tools convertidas
    para o formato que a API da Anthropic espera."""

    def __init__(self, session: ClientSession, allowed_tools: list[str] | None = None):
        self._session = session
        self._allowed_tools = allowed_tools
        self.tools_schema: list[dict[str, Any]] = []
        self.tool_names: list[str] = []

    async def load_tools(self) -> None:
        result = await self._session.list_tools()
        tools = result.tools

        if self._allowed_tools is not None:
            tools = [t for t in tools if t.name in self._allowed_tools]

        self.tool_names = [t.name for t in tools]
        self.tools_schema = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.inputSchema,
            }
            for t in tools
        ]

    async def call_tool(self, name: str, arguments: dict) -> str:
        result = await self._session.call_tool(name, arguments)

        # o retorno pode ter blocos de tipos diferentes (texto, imagem...),
        # aqui só nos interessa o texto
        text_chunks = [
            block.text for block in result.content if getattr(block, "type", None) == "text"
        ]
        return "\n".join(text_chunks) if text_chunks else "(sem retorno em texto)"


@asynccontextmanager
async def connect(url: str, allowed_tools: list[str] | None = None):
    """Abre a conexão streamable HTTP com o Obsidian e entrega um
    ObsidianMCPClient já pronto pra uso.

    Uso:
        async with connect(url) as obsidian:
            ...
    """
    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            client = ObsidianMCPClient(session, allowed_tools)
            await client.load_tools()
            yield client
