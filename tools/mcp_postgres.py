"""Минимальный MCP-сервер для Postgres (stdio). Пример «своего MCP-сервера» для занятия 2.

Права определяет роль в DATABASE_URI: по умолчанию agent_ro (только SELECT).
"""
import os

import psycopg
from mcp.server.mcpserver import MCPServer

server = MCPServer("postgres")
DSN = os.environ["DATABASE_URI"]


@server.tool()
def list_tables() -> str:
    """Список таблиц и колонок в базе демо-сервиса."""
    return query("SELECT table_name, string_agg(column_name || ' ' || data_type, ', ') AS columns "
                 "FROM information_schema.columns WHERE table_schema = 'public' GROUP BY table_name")


@server.tool()
def query(sql: str) -> str:
    """Выполнить SQL-запрос в базе демо-сервиса и вернуть до 50 строк."""
    try:
        with psycopg.connect(DSN, autocommit=True, options="-c statement_timeout=5000") as conn:
            cur = conn.execute(sql)
            if cur.description is None:
                return f"OK, rows affected: {cur.rowcount}"
            cols = [d.name for d in cur.description]
            rows = cur.fetchmany(50)
    except psycopg.Error as e:
        return f"ERROR: {e}"  # текст ошибки БД (например, permission denied) — модели
    return "\n".join([" | ".join(cols)] + [" | ".join(map(str, r)) for r in rows])


if __name__ == "__main__":
    server.run("stdio")
