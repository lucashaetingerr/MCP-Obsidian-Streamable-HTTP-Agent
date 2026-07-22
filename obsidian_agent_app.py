#!/usr/bin/env python3
"""
=============================================================================
 AGENTE DE IA CONFIGURÁVEL - INTEGRADO COM OBSIDIAN (via MCP / Streamable HTTP)
=============================================================================

O que este script faz, em bom português:

  1. Ele abre uma conversa no terminal com um agente de IA (Claude).
  2. Esse agente tem acesso ao seu vault do Obsidian através do protocolo
     MCP (Model Context Protocol), usando o transporte "Streamable HTTP".
     Ou seja: o Obsidian precisa estar rodando com um plugin que exponha
     um servidor MCP em HTTP (ex: "MCP Tools", "Obsidian MCP Server", etc).
  3. O agente decide sozinho quando precisa usar uma ferramenta do Obsidian
     (ex: buscar uma nota, ler o conteúdo, criar/editar arquivos) e o
     script cuida de toda a "burocracia" de chamar essa ferramenta e
     devolver o resultado pro modelo.

Tudo que você provavelmente vai querer mexer está reunido logo abaixo,
na seção "CONFIGURAÇÃO DO AGENTE". Não precisa entender o resto do código
pra customizar o comportamento do seu agente.

-----------------------------------------------------------------------------
COMO USAR:

  1. Instale as dependências:
       pip install anthropic mcp

  2. Defina sua chave de API da Anthropic como variável de ambiente:
       export ANTHROPIC_API_KEY="sua-chave-aqui"

  3. Deixe o Obsidian aberto com o plugin de servidor MCP ativado
     (normalmente ele mostra a URL, algo como http://127.0.0.1:27124/mcp).

  4. Rode o script:
       python3 agente_obsidian.py

  5. Converse com o agente! Digite "sair" para encerrar.
-----------------------------------------------------------------------------
"""

import asyncio
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import anthropic
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


# =============================================================================
# CONFIGURAÇÃO DO AGENTE — MEXA AQUI PARA CUSTOMIZAR
# =============================================================================
#
# Essa é a área "de verdade" para você personalizar. Troque os valores
# abaixo à vontade: nome do agente, personalidade (system prompt), modelo,
# endereço do Obsidian, etc.

@dataclass
class ConfiguracaoDoAgente:
    # Nome que aparece no chat (só estética, pode ser qualquer coisa)
    nome_do_agente: str = "Nôta"

    # A "personalidade" e as instruções do agente. Aqui é onde você define
    # como ele deve se comportar, o tom de voz, o que ele pode ou não fazer.
    # Fique à vontade para reescrever completamente esse texto.
    system_prompt: str = (
        "Você é Nôta, um assistente de IA que ajuda o usuário a organizar, "
        "explorar e escrever notas no Obsidian dele. Você tem acesso direto "
        "ao vault do usuário através de ferramentas (tools). Sempre que for "
        "relevante, use essas ferramentas em vez de inventar informação — "
        "por exemplo, busque ou leia notas reais antes de responder perguntas "
        "sobre o conteúdo do vault. Seja direto, organizado e use listas "
        "em Markdown quando fizer sentido. Se for criar ou editar uma nota, "
        "confirme com o usuário antes, a menos que ele já tenha pedido "
        "explicitamente para você fazer a alteração."
    )

    # Qual modelo da Anthropic usar.
    modelo: str = "claude-sonnet-4-5"

    # Quantos tokens no máximo o agente pode gerar por resposta.
    max_tokens: int = 2048

    # "Criatividade" das respostas: 0 = bem direto e previsível, 1 = mais solto.
    temperatura: float = 0.4

    # Endereço do servidor MCP do Obsidian (streamable HTTP).
    # Ajuste a porta/caminho conforme o plugin que você usa no Obsidian.
    url_mcp_obsidian: str = "http://127.0.0.1:27124/mcp"

    # Lista de nomes de ferramentas que o agente PODE usar.
    # Deixe como None para liberar todas as ferramentas que o Obsidian
    # oferecer. Se quiser restringir, coloque algo como:
    #   ["search_notes", "read_note", "list_notes"]
    ferramentas_permitidas: list[str] | None = None

    # Quantas "idas e vindas" entre o agente e as ferramentas são permitidas
    # numa única resposta, antes de forçar uma resposta final em texto.
    # Evita loops infinitos caso o agente fique chamando ferramentas à toa.
    max_chamadas_de_ferramenta_por_turno: int = 6

    # Mostrar ou não, no terminal, quando o agente está usando uma ferramenta
    # (útil para debug / entender o que ele está fazendo por baixo dos panos).
    mostrar_uso_de_ferramentas: bool = True


# =============================================================================
# A PARTIR DAQUI: o "motor" do agente. Não precisa mexer, mas está comentado
# para quem quiser entender ou avançar na customização.
# =============================================================================


class AgenteObsidian:
    """
    Representa uma sessão de conversa entre o usuário, o Claude e o
    servidor MCP do Obsidian. Guarda o histórico da conversa e sabe como
    traduzir as ferramentas do Obsidian para o formato que o Claude entende.
    """

    def __init__(self, config: ConfiguracaoDoAgente):
        self.config = config
        self.cliente_anthropic = anthropic.Anthropic()
        self.sessao_mcp: ClientSession | None = None
        self.ferramentas_disponiveis: list[dict[str, Any]] = []
        self.historico: list[dict[str, Any]] = []

    # -------------------------------------------------------------------
    # Conexão com o Obsidian via MCP (Streamable HTTP)
    # -------------------------------------------------------------------
    async def conectar_ao_obsidian(self, sessao: ClientSession) -> None:
        """Inicializa a sessão MCP e descobre quais ferramentas o Obsidian oferece."""
        self.sessao_mcp = sessao
        await sessao.initialize()

        resposta = await sessao.list_tools()
        todas_as_ferramentas = resposta.tools

        # Se o usuário restringiu as ferramentas permitidas, filtramos aqui.
        if self.config.ferramentas_permitidas is not None:
            todas_as_ferramentas = [
                ferramenta
                for ferramenta in todas_as_ferramentas
                if ferramenta.name in self.config.ferramentas_permitidas
            ]

        # O Claude espera as ferramentas num formato específico (name,
        # description, input_schema). Convertemos aqui, uma única vez.
        self.ferramentas_disponiveis = [
            {
                "name": ferramenta.name,
                "description": ferramenta.description or "",
                "input_schema": ferramenta.inputSchema,
            }
            for ferramenta in todas_as_ferramentas
        ]

        print(
            f"[{self.config.nome_do_agente}] Conectado ao Obsidian. "
            f"{len(self.ferramentas_disponiveis)} ferramenta(s) disponível(is): "
            + ", ".join(f.name for f in todas_as_ferramentas)
        )

    async def _executar_ferramenta(self, nome: str, argumentos: dict) -> str:
        """Chama uma ferramenta real do Obsidian através da sessão MCP."""
        assert self.sessao_mcp is not None, "Sessão MCP não foi iniciada."

        if self.config.mostrar_uso_de_ferramentas:
            print(f"   🔧 usando ferramenta '{nome}' com argumentos: {argumentos}")

        resultado = await self.sessao_mcp.call_tool(nome, argumentos)

        # O resultado pode vir em blocos de conteúdo (texto, imagem, etc).
        # Aqui simplificamos, juntando só o conteúdo de texto.
        partes_de_texto = [
            bloco.text for bloco in resultado.content if getattr(bloco, "type", None) == "text"
        ]
        return "\n".join(partes_de_texto) if partes_de_texto else "(ferramenta não retornou texto)"

    # -------------------------------------------------------------------
    # Conversa com o Claude
    # -------------------------------------------------------------------
    async def enviar_mensagem(self, texto_do_usuario: str) -> str:
        """
        Envia uma mensagem do usuário para o agente, deixa ele usar as
        ferramentas do Obsidian se precisar, e devolve a resposta final
        em texto.
        """
        self.historico.append({"role": "user", "content": texto_do_usuario})

        for _ in range(self.config.max_chamadas_de_ferramenta_por_turno):
            resposta = self.cliente_anthropic.messages.create(
                model=self.config.modelo,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperatura,
                system=self.config.system_prompt,
                tools=self.ferramentas_disponiveis,
                messages=self.historico,
            )

            # Guardamos a resposta do modelo no histórico (pode conter
            # tanto texto quanto pedidos de uso de ferramenta).
            self.historico.append({"role": "assistant", "content": resposta.content})

            # Se o modelo não pediu nenhuma ferramenta, a conversa deste
            # turno terminou: extraímos e devolvemos o texto final.
            if resposta.stop_reason != "tool_use":
                return self._extrair_texto(resposta.content)

            # Caso contrário, o modelo quer usar uma ou mais ferramentas.
            # Executamos cada uma e devolvemos o resultado pra ele continuar.
            blocos_de_resultado = []
            for bloco in resposta.content:
                if bloco.type == "tool_use":
                    texto_resultado = await self._executar_ferramenta(
                        bloco.name, bloco.input
                    )
                    blocos_de_resultado.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": bloco.id,
                            "content": texto_resultado,
                        }
                    )

            self.historico.append({"role": "user", "content": blocos_de_resultado})

        return (
            "Atingi o limite de chamadas de ferramenta para esta resposta. "
            "Tente reformular sua pergunta de forma mais específica."
        )

    @staticmethod
    def _extrair_texto(blocos_de_conteudo) -> str:
        """Pega só as partes de texto de uma resposta do Claude."""
        return "\n".join(
            bloco.text for bloco in blocos_de_conteudo if bloco.type == "text"
        ).strip()


# =============================================================================
# LOOP DE CONVERSA NO TERMINAL
# =============================================================================

async def rodar_chat(config: ConfiguracaoDoAgente) -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "⚠️  A variável de ambiente ANTHROPIC_API_KEY não está definida.\n"
            "   Defina com: export ANTHROPIC_API_KEY='sua-chave-aqui'"
        )
        sys.exit(1)

    agente = AgenteObsidian(config)

    print(f"Conectando ao Obsidian em {config.url_mcp_obsidian} ...")
    try:
        async with streamablehttp_client(config.url_mcp_obsidian) as (
            leitura,
            escrita,
            _,
        ):
            async with ClientSession(leitura, escrita) as sessao:
                await agente.conectar_ao_obsidian(sessao)

                print(
                    f"\n{config.nome_do_agente} está pronto! "
                    "Digite sua mensagem (ou 'sair' para encerrar).\n"
                )

                while True:
                    try:
                        entrada = input("Você: ").strip()
                    except (EOFError, KeyboardInterrupt):
                        print("\nAté mais!")
                        break

                    if not entrada:
                        continue
                    if entrada.lower() in {"sair", "exit", "quit"}:
                        print("Até mais!")
                        break

                    hora = datetime.now().strftime("%H:%M")
                    resposta = await agente.enviar_mensagem(entrada)
                    print(f"\n{config.nome_do_agente} [{hora}]: {resposta}\n")

    except Exception as erro:
        print(
            "❌ Não consegui conectar ao servidor MCP do Obsidian.\n"
            f"   Detalhe do erro: {erro}\n\n"
            "   Confira se:\n"
            "   - O Obsidian está aberto\n"
            "   - O plugin de servidor MCP está ativado\n"
            "   - A URL configurada em 'url_mcp_obsidian' está correta\n"
        )
        sys.exit(1)


def main() -> None:
    # É AQUI que você escolhe qual configuração usar. Se quiser ter vários
    # "perfis" de agente, basta criar mais instâncias de ConfiguracaoDoAgente
    # e trocar qual delas é passada para rodar_chat().
    config = ConfiguracaoDoAgente()

    asyncio.run(rodar_chat(config))


if __name__ == "__main__":
    main()
