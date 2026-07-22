"""Chat de terminal. `python -m agente_obsidian` cai aqui."""

from __future__ import annotations

import asyncio
import sys

from .agent import Agent, ToolCallLimitReached
from .config import AgentConfig
from .obsidian_client import connect


async def _chat_loop(config: AgentConfig) -> None:
    print(f"conectando em {config.obsidian_mcp_url} ...")

    async with connect(config.obsidian_mcp_url, config.allowed_tools) as obsidian:
        print(f"conectado. tools disponíveis: {', '.join(obsidian.tool_names) or 'nenhuma'}\n")

        agent = Agent(config, obsidian)
        print(f"{config.name} tá de pé. manda a mensagem (ou 'sair' pra encerrar)\n")

        while True:
            try:
                user_input = input("você: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nvaleu, até mais")
                return

            if not user_input:
                continue
            if user_input.lower() in {"sair", "exit", "quit"}:
                print("valeu, até mais")
                return

            try:
                reply = await agent.ask(user_input)
            except ToolCallLimitReached as e:
                reply = f"[não consegui terminar: {e}]"

            print(f"\n{config.name}: {reply}\n")


def main() -> None:
    config = AgentConfig()

    try:
        asyncio.run(_chat_loop(config))
    except RuntimeError as e:
        # normalmente falta de API key, ver AgentConfig.anthropic_api_key
        print(f"erro: {e}")
        sys.exit(1)
    except Exception as e:
        print(
            f"não consegui conectar no Obsidian ({e}).\n"
            "checa se: o Obsidian tá aberto, o plugin do servidor MCP tá "
            "ligado, e a porta em OBSIDIAN_MCP_URL bate com a do plugin."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
