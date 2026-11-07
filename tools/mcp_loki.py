"""Минимальный MCP-сервер для Loki (stdio): логи контейнеров стенда по LogQL."""
import os
import time

import httpx
from mcp.server.mcpserver import MCPServer

server = MCPServer("loki")
LOKI = os.environ.get("LOKI_URL", "http://loki:3100")


@server.tool()
def query_logs(service: str, contains: str = "", minutes: int = 15, limit: int = 50) -> str:
    """Последние строки логов сервиса за N минут.
    service — имя сервиса в docker compose: demo-api, litellm, postgres, ...
    contains — фильтр по подстроке без учёта регистра, например "error" (пусто = все строки)."""
    # ponytail: тул собирает LogQL сам — 7B-модели плохо пишут LogQL; сырой LogQL добавить, если понадобится
    logql = f'{{service="{service}"}}' + (f' |~ "(?i){contains}"' if contains else "")
    now = time.time_ns()
    r = httpx.get(f"{LOKI}/loki/api/v1/query_range", params={
        "query": logql, "start": now - minutes * 60 * 10**9, "end": now, "limit": limit, "direction": "backward"})
    if r.is_error:
        return f"ERROR: {r.text}"
    lines = [v[1] for s in r.json()["data"]["result"] for v in s["values"]]
    return "\n".join(lines) or "нет строк"


if __name__ == "__main__":
    server.run("stdio")
