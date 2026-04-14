FROM node:22-alpine

WORKDIR /app

COPY package.json runner.js agent.js stats.js payment-adapter-canton.js payment-adapter-interface.js tasks.json ./

# Runtime config via env vars
ENV MCP_SERVER_URL=https://mcp-dev1.01.chainsafe.dev
ENV LOOP_INTERVAL=60
ENV STATUS_INTERVAL=60
ENV TASK_INTERVAL=5000
ENV KEY_FILE=/config/key.json

# Key file mounted as volume at /config/key.json
VOLUME /config

CMD node runner.js \
  --key "$KEY_FILE" \
  --server "$MCP_SERVER_URL" \
  --loop \
  --loop-interval "$LOOP_INTERVAL" \
  --status-interval "$STATUS_INTERVAL" \
  --interval "$TASK_INTERVAL"
