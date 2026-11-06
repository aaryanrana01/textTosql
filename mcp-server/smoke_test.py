"""Starts the MCP server over stdio, the way an AI assistant does, lists its tools and calls them.
Usage: python mcp-server/smoke_test.py ["optional real question"]"""
import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, MCPError, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parent / "server.py"


def text_of(result) -> str:
    prefix = "TOOL ERROR: " if result.is_error else ""
    return prefix + (result.content[0].text if result.content else "(no content)")


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("Tools offered:", [t.name for t in tools.tools])

            calls = [
                ("describe_database", {}),
                ("list_business_terms", {}),
                ("ask_database", {"question": "Delete all rentals."}),  # refused before the LLM: 0 tokens
            ]
            if len(sys.argv) > 1:
                calls.append(("ask_database", {"question": sys.argv[1]}))

            for name, args in calls:
                try:
                    result = await session.call_tool(name, args)
                    print(f"\n--- {name}({args.get('question', '')}) ->\n{text_of(result)[:800]}")
                except MCPError as exc:
                    print(f"\n--- {name} -> PROTOCOL ERROR {exc.code}: {exc.message}")


asyncio.run(main())