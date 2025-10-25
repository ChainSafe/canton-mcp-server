# MCP Test Container - Makes irregular MCP tool calls for testing
FROM python:3.12-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy test script
COPY mcp_tester.py .

# Set default environment variables
ENV MCP_SERVER_URL=http://canton-mcp-server:7284/mcp
ENV MIN_INTERVAL=30
ENV MAX_INTERVAL=300

# Run the test script
CMD ["python", "-u", "mcp_tester.py"]

