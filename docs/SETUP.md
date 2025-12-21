# Setup & Deployment Guide

## Prerequisites

- Python 3.10+
- Docker & Docker Compose
- Ollama (for LLM) or access to HPC cluster

## Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd WayfindR-LLM
```

### 2. Start Docker Services

```bash
docker-compose up -d
```

This starts:
- **Qdrant** (vector database) on port 6333
- **PostgreSQL** (message storage) on port 5432

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

**Key dependencies:**
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `qdrant-client` - Qdrant vector database
- `psycopg2-binary` - PostgreSQL driver
- `ollama` - LLM client
- `jinja2` - Template engine

### 4. Configure Environment

Create a `.env` file or set environment variables:

```bash
# Server Configuration
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Qdrant Configuration
QDRANT_HOST=localhost
QDRANT_PORT=6333

# PostgreSQL Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=wayfindr
POSTGRES_USER=wayfindr
POSTGRES_PASSWORD=wayfindr

# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.3:70b
```

### 5. Configure LLM

**Option A: Local Ollama**

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull model
ollama pull llama3.3:70b

# Or use the provided script
./launch_ollama.sh
```

**Option B: Remote Ollama (HPC)**

Edit `llm_config.py`:

```python
OLLAMA_HOST = "http://your-hpc-node:11434"
```

### 6. Start the Server

```bash
python main.py
```

Or with uvicorn directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 7. Access the Dashboard

Open in browser:
- **Dashboard**: http://localhost:8000
- **Live Map**: http://localhost:8000/map
- **Health Check**: http://localhost:8000/health

## Docker Compose Details

```yaml
version: '3.8'
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

  postgres:
    image: postgres:15
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: wayfindr
      POSTGRES_USER: wayfindr
      POSTGRES_PASSWORD: wayfindr
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  qdrant_data:
  postgres_data:
```

## Directory Structure Setup

Ensure these directories exist:

```bash
mkdir -p data
mkdir -p static/css
mkdir -p static/js
mkdir -p templates
mkdir -p docs
```

## Initial Map Configuration

The system creates default map configuration on first run. To customize:

1. Edit `data/map_config.json` directly, or
2. Use the API endpoints, or
3. Use the web map interface

**Default configuration includes:**
- One floor ("Ground Floor")
- Sample waypoints (lobby, reception, etc.)
- No blocked zones

## Verifying Installation

### Check Health Endpoint

```bash
curl http://localhost:8000/health
```

**Expected response:**
```json
{
    "mcp_server": "online",
    "llm": "ready",
    "qdrant": "available",
    "postgresql": "available",
    "active_robots": 0,
    "timestamp": "2024-01-15T10:30:00"
}
```

### Test Telemetry

```bash
curl -X POST http://localhost:8000/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "robot_id": "test_robot",
    "telemetry": {
      "battery": 85,
      "status": "idle",
      "current_location": "lobby"
    }
  }'
```

### Test Chat

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What robots are online?",
    "user_id": "test_user"
  }'
```

## Production Deployment

### Using Gunicorn

```bash
pip install gunicorn

gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

### Using systemd

Create `/etc/systemd/system/wayfindr.service`:

```ini
[Unit]
Description=WayfindR-LLM Server
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/wayfindr-llm
ExecStart=/opt/wayfindr-llm/venv/bin/gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable wayfindr
sudo systemctl start wayfindr
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name wayfindr.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # SSE endpoints need longer timeout
    location /stream/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400;
    }
}
```

## Troubleshooting

### Qdrant Connection Failed

```
Error: Connection refused to Qdrant
```

**Solution:**
```bash
docker-compose up -d qdrant
# Wait a few seconds for startup
docker-compose logs qdrant
```

### PostgreSQL Connection Failed

```
Error: Connection refused to PostgreSQL
```

**Solution:**
```bash
docker-compose up -d postgres
# Check logs
docker-compose logs postgres
```

### LLM Not Available

```
[MCP] LLM not available
```

**Solutions:**
1. Check Ollama is running: `curl http://localhost:11434/api/tags`
2. Check model is pulled: `ollama list`
3. Verify `OLLAMA_HOST` in configuration

### Import Errors

```
ModuleNotFoundError: No module named 'xyz'
```

**Solution:**
```bash
pip install -r requirements.txt
```

### Template Not Found

```
TemplateNotFoundError: index.html
```

**Solution:**
Ensure `templates/` directory exists and contains HTML files.

## Logs

Application logs are printed to stdout. For production, redirect to file:

```bash
python main.py 2>&1 | tee -a /var/log/wayfindr.log
```

Or configure logging in `main.py`:

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    filename='/var/log/wayfindr.log',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## Backup

### Qdrant Data

```bash
docker-compose exec qdrant qdrant-backup --output /backup
docker cp qdrant:/backup ./qdrant_backup
```

### PostgreSQL Data

```bash
docker-compose exec postgres pg_dump -U wayfindr wayfindr > backup.sql
```

### Map Configuration

```bash
cp data/map_config.json data/map_config_backup.json
```

## Updating

```bash
git pull
pip install -r requirements.txt
sudo systemctl restart wayfindr
```

## Robot Integration Checklist

For each robot to connect:

1. Configure robot to send telemetry to `/telemetry`
2. Set unique `robot_id` in telemetry payload
3. Configure robot to query `/map/state/{robot_id}` for navigation
4. (Optional) Configure chat endpoint for visitor interaction

**Telemetry format:**
```json
{
    "robot_id": "robot_01",
    "telemetry": {
        "battery": 85,
        "status": "idle",
        "current_location": "lobby",
        "position": {"x": 100, "y": 200},
        "floor_id": "floor_1"
    }
}
```
