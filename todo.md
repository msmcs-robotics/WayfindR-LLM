# WayfindR-LLM Development Roadmap

Last Updated: 2025-12-22

## Latest Test Results

**Date:** December 22, 2025
**Pass Rate:** 94.7% (18/19 tests passed)
**Details:** [docs/tests/2025-12-22-comprehensive-test.md](docs/tests/2025-12-22-comprehensive-test.md)

| Category | Status |
|----------|--------|
| Health & System | All passing |
| Telemetry Endpoints | All passing |
| Robot Management | All passing |
| Map Endpoints | 5/6 (map file expected missing) |
| Chat Endpoints | All passing |
| Semantic Search | All passing |
| Data Retrieval | All passing |

---

## Completed Features

### Core Infrastructure
- [x] Ollama-based embeddings (all-minilm:l6-v2, 384 dimensions)
- [x] PostgreSQL + Qdrant vector stores
- [x] LLM integration (llama3.3:70b-instruct via Ollama)
- [x] FastAPI server with automatic API docs

### API Endpoints
- [x] `/health` - System status check
- [x] `/telemetry` - Robot telemetry ingestion
- [x] `/telemetry/status` - Current robot status
- [x] `/telemetry/history/{robot_id}` - Telemetry history
- [x] `/telemetry/stats` - Collection statistics
- [x] `/robots` - Robot fleet management
- [x] `/map/floors`, `/map/waypoints`, `/map/zones` - Spatial data
- [x] `/map/robots/positions` - Coordinate-to-pixel conversion
- [x] `/map/image/*` - ROS2 SLAM map serving
- [x] `/search/telemetry`, `/search/messages` - Semantic search
- [x] `/chat`, `/robot_chat` - LLM-powered conversations
- [x] `/ws/telemetry` - WebSocket real-time updates
- [x] `/data/qdrant`, `/data/postgresql` - Raw data access

---

## Priority 1: ROS2 Integration

The next phase is connecting to the actual WayfindR robot fleet.

### Robot Driver Integration
- [ ] Define ROS2 telemetry message schema
- [ ] Create ROS2 node that publishes to `/telemetry` endpoint
- [ ] Test with actual robot coordinates
- [ ] Verify LiDAR map coordinate system alignment

### Map Configuration
- [ ] Deploy actual SLAM maps (PGM/YAML) to `data/maps/`
- [ ] Configure map origin, resolution in YAML files
- [ ] Test coordinate-to-pixel conversion with real positions

### Live Map Viewer
- [ ] Connect map.html to `/ws/telemetry` WebSocket
- [ ] Overlay robot icons at pixel positions
- [ ] Add robot status indicators (battery, state)
- [ ] Show movement trails

---

## Priority 2: Operational Features

### Alert System
- [ ] Low battery detection (<20% threshold)
- [ ] Stuck robot detection (no movement for N minutes)
- [ ] Zone violation alerts
- [ ] WebSocket push to operator dashboard

### Zone Management
- [ ] Persist zones to `data/zones.json`
- [ ] Auto-load zones on startup
- [ ] Zone expiration/scheduling
- [ ] Geo-fence enforcement

### Telemetry Retention
- [ ] Automatic cleanup of old data (configurable hours)
- [ ] Scheduled cleanup task
- [ ] Data export for analysis

---

## Priority 3: LLM Enhancements

### Chat Improvements
- [ ] Streaming responses (SSE)
- [ ] Conversation memory (last N messages)
- [ ] Per-robot system prompts
- [ ] Intent classification for commands

### RAG Improvements
- [ ] Embed more context (zone definitions, waypoints)
- [ ] Better search result ranking
- [ ] Query expansion for better recall

---

## Priority 4: Multi-Floor & Scaling

### Multi-Floor Support
- [ ] Multiple floor map configurations
- [ ] Floor switching in UI
- [ ] Elevator waypoint connections
- [ ] Cross-floor navigation context

### Performance
- [ ] Load testing telemetry ingestion rate
- [ ] Connection pooling for databases
- [ ] Embedding batch processing

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    WayfindR-LLM Server                      │
│                    (FastAPI on :5000)                       │
├─────────────────────────────────────────────────────────────┤
│  REST Endpoints:                                            │
│  ├── /health              System status                     │
│  ├── /chat                Operator chat (LLM)               │
│  ├── /robot_chat          Visitor/robot chat (LLM)          │
│  ├── /telemetry/*         Robot telemetry                   │
│  ├── /robots/*            Fleet management                  │
│  ├── /map/*               Floors, waypoints, zones, images  │
│  ├── /search/*            Semantic search                   │
│  └── /data/*              Raw data access                   │
│                                                             │
│  WebSocket:                                                 │
│  └── /ws/telemetry        Real-time position updates        │
├─────────────────────────────────────────────────────────────┤
│  Storage:                                                   │
│  ├── Qdrant (:6333)       Telemetry vectors (384d)          │
│  └── PostgreSQL (:5435)   Messages, logs (pgvector)         │
├─────────────────────────────────────────────────────────────┤
│  AI/LLM (Ollama via tunnel):                                │
│  ├── llama3.3:70b         Chat & commands                   │
│  └── all-minilm:l6-v2     Embeddings                        │
└─────────────────────────────────────────────────────────────┘
           │
           │ HTTP/WebSocket
           ▼
┌─────────────────────────────────────────────────────────────┐
│                    WayfindR Robot Fleet                     │
│                    (ROS2 Humble)                            │
├─────────────────────────────────────────────────────────────┤
│  Each robot publishes:                                      │
│  ├── Position (x, y, theta)                                 │
│  ├── Battery level                                          │
│  ├── Navigation status                                      │
│  └── Current location name                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Reference

### Local Development
```bash
# Activate environment
cd /home/devel/WayfindR-LLM
source venv/bin/activate

# Start server
python main.py

# Run tests
./scripts/run_tests.sh http://localhost:5000

# View API docs
# Open: http://localhost:5000/docs
```

### Remote Deployment
```bash
# Sync to remote
rsync -avz --exclude '__pycache__' --exclude '.git' --exclude 'venv' \
  /home/devel/WayfindR-LLM/ devel@192.168.0.7:~/Desktop/WayfindR-LLM/

# Start on remote
ssh devel@192.168.0.7 "cd ~/Desktop/WayfindR-LLM && source venv/bin/activate && python main.py"
```

### Ollama Tunnel (for HPC LLM access)
```bash
ssh -L 11434:localhost:11434 hpc-cluster
```

### Database Containers
```bash
# Qdrant
docker start rag_qdrant  # Port 6333

# PostgreSQL
docker start rag_pg      # Port 5435
```

---

## Notes

- Embeddings are 384-dimensional via Ollama's all-minilm:l6-v2
- All AI processing offloaded to HPC via SSH tunnel
- Map coordinates use ROS2 standard: `pixel = (world - origin) / resolution`
- WebSocket broadcasts on telemetry updates for real-time tracking
