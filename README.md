# mcp-ssh-multi

MCP server for managing multiple SSH servers through AI assistants. Provides 11 tools for remote command execution, file operations, and system monitoring.

## Features

- **Multi-server management** — Configure and manage multiple SSH servers from a single YAML file
- **Connection pooling** — Automatic connection reuse and reconnection
- **11 MCP tools** — Execute commands, transfer files, read/write files, tail logs, list processes
- **Two transports** — stdio (for local MCP clients) and streamable-http (for web/remote)
- **Cloudflare Tunnel compatible** — Deploy behind a tunnel for remote access

## Installation

### Using uv (recommended)

```bash
uv tool install mcp-ssh-multi
```

### Using pip

```bash
pip install mcp-ssh-multi
```

### Using uvx (one-shot)

```bash
uvx --from mcp-ssh-multi ssh-mcp
```

### From source

```bash
git clone https://github.com/gilberth/mcp-ssh-multi.git
cd mcp-ssh-multi
uv sync
```

## Configuration

### 1. SSH Servers (ssh_servers.yaml)

Create a `ssh_servers.yaml` file with your server definitions:

```yaml
servers:
  proxmox:
    host: 192.168.1.100
    port: 22
    username: root
    key_file: ~/.ssh/id_rsa
    description: "Proxmox VE hypervisor"

  truenas:
    host: 192.168.1.101
    port: 22
    username: root
    password: "my-password"  # or use key_file
    description: "TrueNAS storage server"
```

### 2. Environment Variables (.env)

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `SSH_SERVERS_FILE` | `ssh_servers.yaml` | Path to servers config |
| `SSH_TIMEOUT` | `30` | Default command timeout (seconds) |
| `LOG_LEVEL` | `INFO` | Logging level |
| `MCP_PORT` | `8086` | HTTP server port |
| `MCP_SECRET_PATH` | `/mcp` | HTTP endpoint path |

## Usage

### stdio mode (local MCP clients)

```bash
ssh-mcp
```

Or with uvx:

```bash
uvx --from mcp-ssh-multi ssh-mcp
```

### HTTP mode (web/remote MCP clients)

```bash
ssh-mcp-web
```

The server will listen on `http://0.0.0.0:8086/mcp` by default.

### MCP Client Configuration

Add to your MCP client config (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "ssh": {
      "command": "uvx",
      "args": ["--from", "mcp-ssh-multi", "ssh-mcp"],
      "env": {
        "SSH_SERVERS_FILE": "/path/to/ssh_servers.yaml"
      }
    }
  }
}
```

For HTTP mode:

```json
{
  "mcpServers": {
    "ssh": {
      "url": "http://localhost:8086/mcp"
    }
  }
}
```

## Tool Reference

### Connection Management

| Tool | Description |
|------|-------------|
| `ssh_list_servers` | List all configured servers with connection status |
| `ssh_disconnect` | Disconnect from a specific server |

### Command Execution

| Tool | Description |
|------|-------------|
| `ssh_execute` | Execute a shell command on a remote server |

### File Operations

| Tool | Description |
|------|-------------|
| `ssh_upload` | Upload a local file to a remote server |
| `ssh_download` | Download a file from a remote server |
| `ssh_file_exists` | Check if a file/directory exists on a server |
| `ssh_list_dir` | List contents of a remote directory |
| `ssh_read_file` | Read a text file from a remote server |
| `ssh_write_file` | Write content to a file on a remote server |

### System Monitoring

| Tool | Description |
|------|-------------|
| `ssh_tail_log` | Tail a log file on a remote server |
| `ssh_process_list` | List running processes (optionally filtered) |

## Cloudflare Tunnel Deployment

You can expose the HTTP mode behind a Cloudflare Tunnel for secure remote access. The tunnel is **not part of this package** — it runs separately.

### Quick Start

```bash
# 1. Start ssh-mcp-web
SSH_SERVERS_FILE=/path/to/ssh_servers.yaml ssh-mcp-web

# 2. In another terminal, start the tunnel
cloudflared tunnel --url http://localhost:8086
```

### Permanent Tunnel

```bash
# Create a named tunnel
cloudflared tunnel create ssh-mcp
cloudflared tunnel route dns ssh-mcp ssh-mcp.yourdomain.com

# Configure the tunnel (config.yml)
# tunnel: <tunnel-id>
# credentials-file: /root/.cloudflared/<tunnel-id>.json
# ingress:
#   - hostname: ssh-mcp.yourdomain.com
#     service: http://localhost:8086
#   - service: http_status:404

# Run it
cloudflared tunnel run ssh-mcp
```

Then configure your MCP client to connect to `https://ssh-mcp.yourdomain.com/mcp`.

### Environment Variables for Tunnel

```bash
MCP_PORT=8086           # Port the HTTP server listens on
MCP_SECRET_PATH=/mcp    # Endpoint path (change for obscurity)
```

## Development

```bash
# Install with dev dependencies
uv sync --group dev

# Run linting
uv run ruff check src/ tests/ --fix
uv run ruff format src/ tests/

# Run type checking
uv run mypy src/

# Run tests
uv run pytest tests/ -v
```

## License

MIT
