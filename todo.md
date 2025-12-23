# WayfindR-LLM Todo List

Last Updated: 2025-12-22

## Completed Tasks

- [x] Update qdrant_store to use Ollama embeddings (all-minilm:l6-v2)
- [x] Update postgresql_store to use Ollama embeddings
- [x] Add embedding model config to llm_config.py
- [x] Deploy and test on remote system (192.168.0.7)
- [x] Remove sentence_transformers dependency (offload to HPC via Ollama)
- [x] Add map image endpoints (/map/image/config, /map/image/list)
- [x] Convert ROS2 SLAM PGM maps to PNG for web display

---

## High Priority

### 1. Implement Missing API Endpoints
The following endpoints returned 404 during testing:
- [ ] `GET /floors` - List building floors
- [ ] `GET /waypoints` - List available waypoints (currently only in config.py)
- [ ] `GET /zones` - List restricted/blocked zones
- [ ] `POST /zones` - Create new zones
- [ ] `DELETE /zones/{zone_id}` - Remove zones

### 2. Robot Position Plotting on Map
- [ ] Implement coordinate-to-pixel conversion using map metadata:
  - Resolution: 0.05 m/pixel
  - Origin: [-4.88, -4.09, 0]
  - Image size: 212x144 pixels
- [ ] Create endpoint to get robot positions in pixel coordinates
- [ ] Add frontend JavaScript to plot robot markers on map image

### 3. Live Map Viewer
- [ ] Create WebSocket endpoint for real-time telemetry updates
- [ ] Build simple HTML/JS dashboard showing:
  - Map with robot positions
  - Robot status cards (battery, status, location)
  - Recent activity log
- [ ] Auto-refresh telemetry every 1-2 seconds

---

## Medium Priority

### 4. Semantic Search API
- [ ] Expose telemetry semantic search via API endpoint
- [ ] Example: `GET /telemetry/search?q=robots with low battery`
- [ ] Add message search: `GET /messages/search?q=navigation commands`

### 5. LLM Integration Improvements
- [ ] Test with active Ollama SSH tunnel
- [ ] Add retry logic for LLM timeouts
- [ ] Implement streaming responses for chat endpoints
- [ ] Add context from conversation history to LLM prompts

### 6. Telemetry Enhancements
- [ ] Define complete telemetry schema for WayfindR-driver integration
- [ ] Add sensor data fields (LiDAR, ultrasonic, etc.)
- [ ] Implement telemetry retention/cleanup (older than 24h)
- [ ] Add aggregation endpoints (avg battery by hour, etc.)

---

## Low Priority

### 7. Zone Management
- [ ] Visual zone editor on map
- [ ] Zone types: blocked, slow, charging, tour-stop
- [ ] Persist zones to database
- [ ] Notify robots when entering/exiting zones

### 8. Multi-Floor Support
- [ ] Floor model with map per floor
- [ ] Floor switching in UI
- [ ] Elevator waypoints connecting floors

### 9. Documentation
- [ ] API documentation (OpenAPI/Swagger is available at /docs)
- [ ] Deployment guide for remote systems
- [ ] Integration guide for WayfindR-driver

### 10. Testing & CI
- [ ] Unit tests for RAG stores
- [ ] Integration tests for API endpoints
- [ ] Automated test runner script

---

## Architecture Notes

### Current Stack
- **Backend**: FastAPI (Python 3.10)
- **Telemetry Store**: Qdrant (vector DB with 384-dim embeddings)
- **Message Store**: PostgreSQL (with optional pgvector)
- **LLM**: Ollama on HPC (llama3.3:70b-instruct-q5_K_M)
- **Embeddings**: Ollama all-minilm:l6-v2 (384 dimensions)
- **Maps**: ROS2 SLAM (PGM + YAML, converted to PNG)

### Remote Deployment
- Host: 192.168.0.7 (Ubuntu 22.04)
- Docker: wayfind_qdrant, wayfind_pg
- Venv: ~/Desktop/WayfindR-LLM/venv
- Sync: `rsync -avz --exclude venv --exclude __pycache__ ...`

### Integration with WayfindR-driver
- Driver app runs on robot (Raspberry Pi or test system)
- Publishes telemetry to `/telemetry` endpoint
- Receives commands via polling or future WebSocket

---

## Quick Commands

```bash
# Sync to remote
rsync -avz --exclude '__pycache__' --exclude '.git' --exclude 'venv' \
  /home/devel/WayfindR-LLM/ devel@192.168.0.7:~/Desktop/WayfindR-LLM/

# Start server on remote
ssh devel@192.168.0.7 "cd ~/Desktop/WayfindR-LLM && source venv/bin/activate && python main.py"

# Check health
curl http://192.168.0.7:5000/health

# View API docs
# Open: http://192.168.0.7:5000/docs
```

---

## Test Results
See [docs/tests/](docs/tests/) for detailed test reports.
