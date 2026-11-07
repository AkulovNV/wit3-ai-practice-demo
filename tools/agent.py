"""Простейший агент: цикл «модель → вызов тула → результат → модель» поверх LiteLLM.

  python agent.py "сколько заказов у пользователя 2?"            # один тул: HTTP GET к demo-api
  python agent.py --mcp prometheus,loki "что сломалось?"  # тулы из MCP-серверов

ALLOWED_TOOLS=postgres__list_tables,git__git_log — allowlist тулов (занятие 3).
"""
import argparse
import asyncio
import json
import os
import uuid
from contextlib import AsyncExitStack

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI

SYSTEM = ("Ты — инженер, который отвечает на вопросы о сервисе shop (FastAPI + Postgres). "
          "Используй тулы, чтобы получить факты, не выдумывай. Отвечай кратко, по-русски. "
          f"Git-репозиторий (repo_path для git-тулов): {os.environ.get('GIT_REPO', '/workspace')}")

MCP_SERVERS = {
    "git": StdioServerParameters(command="mcp-server-git", args=["--repository", os.environ.get("GIT_REPO", "/workspace")]),
    "postgres": StdioServerParameters(command="python", args=["/app/mcp_postgres.py"],
                                      env={"DATABASE_URI": os.environ.get("DATABASE_URI", "")}),
    "loki": StdioServerParameters(command="python", args=["/app/mcp_loki.py"]),
    "prometheus": StdioServerParameters(command="prometheus-mcp-server",
                                        env={"PROMETHEUS_URL": os.environ.get("PROMETHEUS_URL", ""), "PATH": os.environ["PATH"]}),
}

HTTP_TOOL = {"type": "function", "function": {
    "name": "demo_api_get",
    "description": "HTTP GET к API сервиса shop. Эндпоинты: /products?page=&size=, /products/search?name=, "
                   "/products/{id}/reviews, /users/{id}, /users/{id}/orders, /health",
    "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "путь, например /users/1/orders"}},
                   "required": ["path"]}}}


async def http_get(path):
    async with httpx.AsyncClient(base_url=os.environ.get("DEMO_API_URL", "http://demo-api:8000"), timeout=30) as c:
        r = await c.get(path)
        return f"HTTP {r.status_code}\n{r.text}"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--mcp", help="через запятую: " + ",".join(MCP_SERVERS))
    ap.add_argument("--model", default="local-general")
    ap.add_argument("--max-steps", type=int, default=8)
    args = ap.parse_args()

    llm = AsyncOpenAI(base_url=os.environ.get("LITELLM_BASE_URL", "http://litellm:4000") + "/v1",
                      api_key=os.environ["LITELLM_USER_KEY"])
    allowed = {t for t in os.environ.get("ALLOWED_TOOLS", "").split(",") if t}

    async with AsyncExitStack() as stack:
        tools, handlers = [], {}
        if args.mcp:
            for name in args.mcp.split(","):
                read, write = await stack.enter_async_context(stdio_client(MCP_SERVERS[name], errlog=open(os.devnull, "w")))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                for t in (await session.list_tools()).tools:
                    full = f"{name}__{t.name}"
                    tools.append({"type": "function", "function": {
                        "name": full, "description": t.description or "", "parameters": t.input_schema}})
                    handlers[full] = (lambda s, n: lambda a: s.call_tool(n, a))(session, t.name)
        else:
            tools.append(HTTP_TOOL)
            handlers["demo_api_get"] = lambda a: http_get(a["path"])
        if allowed:
            tools = [t for t in tools if t["function"]["name"] in allowed]
        print("tools:", ", ".join(t["function"]["name"] for t in tools))

        trace_id = str(uuid.uuid4())  # все шаги агента — один трейс в Langfuse
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": args.question}]
        for step in range(args.max_steps):
            resp = await llm.chat.completions.create(
                model=args.model, messages=messages, tools=tools,
                extra_body={"metadata": {"trace_id": trace_id, "trace_name": "agent", "generation_name": f"step-{step}"}})
            msg = resp.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls:
                print("\n" + (msg.content or f"(модель вернула пустой ответ, finish_reason={resp.choices[0].finish_reason})"))
                return
            for call in msg.tool_calls:
                name = call.function.name
                print(f"→ {name}({call.function.arguments})")
                # ошибку (кривой JSON аргументов, падение тула) возвращаем модели — пусть исправится сама
                try:
                    a = json.loads(call.function.arguments or "{}")
                    if name not in handlers or (allowed and name not in allowed):
                        out = f"tool {name} is not allowed"
                    else:
                        res = await handlers[name](a)
                        out = res if isinstance(res, str) else "\n".join(getattr(c, "text", str(c)) for c in res.content)
                except Exception as e:
                    out = f"ERROR: {type(e).__name__}: {e}"
                print("  ", out[:300].replace("\n", "\n   "))
                messages.append({"role": "tool", "tool_call_id": call.id, "content": out[:4000]})
        print("\n(лимит шагов исчерпан)")


if __name__ == "__main__":
    asyncio.run(main())
