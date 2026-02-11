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

## Production Deployment (LXC + Cloudflare Tunnel)

Full deployment guide for running mcp-ssh-multi as a systemd service behind a Cloudflare Tunnel on a Proxmox LXC container.

### Prerequisites

- A Proxmox LXC container (Debian 12/13)
- A Cloudflare account with a domain
- `uv` and `cloudflared` installed on the LXC

### 1. Install dependencies

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb \
  -o cloudflared.deb && dpkg -i cloudflared.deb
```

### 2. Create SSH servers config

```bash
mkdir -p /ssh-mcp
cat > /ssh-mcp/ssh_servers.yaml << 'EOF'
servers:
  my-server:
    host: 192.168.1.100
    port: 22
    username: root
    password: "my-password"  # or use key_file
    description: "My server"
EOF
```

### 3. Create the Cloudflare Tunnel

```bash
# Login to Cloudflare (opens browser)
cloudflared tunnel login

# Create the named tunnel
cloudflared tunnel create ssh-mcp

# Route DNS to your domain
cloudflared tunnel route dns ssh-mcp ssh-mcp.yourdomain.com
```

### 4. Configure the tunnel

The `tunnel create` command outputs the tunnel UUID (e.g. `2687c640-38df-40f9-...`) and creates a credentials file at `/root/.cloudflared/<TUNNEL-ID>.json`. If you need to find it later, run `cloudflared tunnel list`.

```bash
# Replace <TUNNEL-ID> with the UUID from "cloudflared tunnel create" output
cat > /root/.cloudflared/config.yml << 'EOF'
tunnel: <TUNNEL-ID>
credentials-file: /root/.cloudflared/<TUNNEL-ID>.json

ingress:
  - hostname: ssh-mcp.yourdomain.com
    service: http://localhost:8086
  - service: http_status:404
EOF
```

### 5. Create systemd services

**mcp-ssh-multi service:**

```bash
cat > /etc/systemd/system/mcp-ssh-multi.service << 'EOF'
[Unit]
Description=MCP SSH Multi Server
After=network.target

[Service]
Type=simple
Environment=SSH_SERVERS_FILE=/ssh-mcp/ssh_servers.yaml
Environment=MCP_SECRET_PATH=/your-secret-path
ExecStart=/root/.local/bin/uvx --from mcp-ssh-multi@latest ssh-mcp-web
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

**cloudflared service:**

```bash
cloudflared service install
```

**Enable and start both:**

```bash
systemctl daemon-reload
systemctl enable --now mcp-ssh-multi
systemctl enable --now cloudflared
```

### 6. Verify

```bash
# Check services
systemctl status mcp-ssh-multi
systemctl status cloudflared

# Test the endpoint
curl -s -X POST "https://ssh-mcp.yourdomain.com/your-secret-path" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

### 7. Configure your MCP client

```json
{
  "mcpServers": {
    "ssh": {
      "type": "remote",
      "url": "https://ssh-mcp.yourdomain.com/your-secret-path"
    }
  }
}
```

### Service management

```bash
# View logs
journalctl -u mcp-ssh-multi -f
journalctl -u cloudflared -f

# Restart services
systemctl restart mcp-ssh-multi
systemctl restart cloudflared
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SSH_SERVERS_FILE` | `ssh_servers.yaml` | Path to servers config |
| `SSH_TIMEOUT` | `30` | Default command timeout (seconds) |
| `LOG_LEVEL` | `INFO` | Logging level |
| `MCP_PORT` | `8086` | HTTP server port |
| `MCP_SECRET_PATH` | `/mcp` | HTTP endpoint path (use a secret value) |

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
