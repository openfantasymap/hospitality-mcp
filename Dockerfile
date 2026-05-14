FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

ENV MCP_HOST=0.0.0.0 \
    MCP_PORT=8750 \
    MCP_PATH=/mcp

EXPOSE 8750

CMD ["python", "server.py"]
