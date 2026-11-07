FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory '*'
RUN pip install --no-cache-dir uv==0.9.5
# MCP-серверы — каждый в своём изолированном окружении (uv tool), бинарники в /usr/local/bin
ENV UV_TOOL_BIN_DIR=/usr/local/bin UV_TOOL_DIR=/opt/uv-tools
RUN uv tool install mcp-server-git==2026.11.4 \
 && uv tool install prometheus-mcp-server==1.6.2
RUN pip install --no-cache-dir openai==3.46.0 mcp==2.3.0 httpx==0.28.1 "psycopg[binary]==3.2.9"
WORKDIR /app
COPY *.py ./
CMD ["python", "agent.py", "--help"]
