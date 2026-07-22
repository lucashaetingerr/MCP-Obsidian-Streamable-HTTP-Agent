"""Loop de conversa: manda a mensagem pro Claude, deixa ele pedir tools
do Obsidian quando precisar, executa e devolve o resultado até sair uma
resposta em texto.
"""

from __future__ import annotations

import anthropic

from .config import AgentConfig
from .obsidian_client import ObsidianMCPClient


class ToolCallLimitReached(Exception):
    """Levantada quando o agente estoura o limite de chamadas de tool
    num único turno — normalmente sinal de que ele entrou em loop."""


class Agent:
    def __init__(self, config: AgentConfig, obsidian: ObsidianMCPClient):
        self.config = config
        self.obsidian = obsidian
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key())
        self.history: list[dict] = []

    async def ask(self, user_message: str) -> str:
        self.history.append({"role": "user", "content": user_message})

        for _ in range(self.config.max_tool_calls_per_turn):
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                system=self.config.system_prompt,
                tools=self.obsidian.tools_schema,
                messages=self.history,
            )
            self.history.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                return self._as_text(response.content)

            self.history.append(
                {"role": "user", "content": await self._run_tool_calls(response.content)}
            )

        raise ToolCallLimitReached(
            f"mais de {self.config.max_tool_calls_per_turn} chamadas de tool "
            "num único turno — abortando pra não ficar em loop"
        )

    async def _run_tool_calls(self, content_blocks) -> list[dict]:
        results = []
        for block in content_blocks:
            if block.type != "tool_use":
                continue

            if self.config.verbose_tool_calls:
                print(f"  -> {block.name}({block.input})")

            output = await self.obsidian.call_tool(block.name, block.input)
            results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": output}
            )
        return results

    @staticmethod
    def _as_text(content_blocks) -> str:
        return "\n".join(b.text for b in content_blocks if b.type == "text").strip()
