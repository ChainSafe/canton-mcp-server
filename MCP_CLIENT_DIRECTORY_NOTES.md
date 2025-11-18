# MCP Client Directory Handling

## The Challenge

When an MCP client (like Cursor) calls the `daml_automater` tool, the MCP server doesn't automatically know the client's working directory. The server runs in its own process with its own working directory.

## Current Solution

**Require explicit absolute paths for `project_path`**

Actions that need to access the filesystem (`run_tests`, `build_dar`) now require `project_path` to be explicitly provided in the config:

```json
{
  "action": "run_tests",
  "config": {
    "project_path": "/Users/you/workspace/my-daml-project"
  }
}
```

## Why Not Automatic?

1. **MCP Protocol Limitation:** The MCP protocol doesn't include a standard field for "client working directory"
2. **Security:** Automatically using client paths could be a security risk
3. **Multi-client:** Server might handle multiple clients in different directories

## Possible Future Solutions

### Option 1: Cursor-Specific Context
If Cursor's MCP implementation provides workspace context, we could:
```python
# Hypothetical - if Cursor passes workspace in context
workspace = ctx.get_workspace_path()
project_path = config.get('project_path', workspace)
```

### Option 2: Environment Variable
Client could set an env var before starting the server:
```bash
export MCP_CLIENT_WORKSPACE="/Users/you/workspace"
uv run canton-mcp-server
```

### Option 3: Convention-Based
Use a well-known location or config file that maps client IDs to directories.

### Option 4: Extended MCP Protocol
Propose extension to MCP that includes client context in requests.

## Recommendation

**For now:** Explicit `project_path` is the most reliable and transparent approach. It makes the requirement clear and avoids assumptions.

**For future:** Monitor MCP protocol development for standardized context passing.

## User Experience

When clients call the tool without `project_path`:

```json
{
  "success": false,
  "action": "run_tests",
  "message": "❌ Missing required config: project_path (must be absolute path to DAML project)",
  "details": {
    "error": "project_path is required",
    "example": {"project_path": "/Users/you/my-daml-project"}
  }
}
```

This provides clear guidance on what's needed.

