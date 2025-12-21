# WayfindR-LLM Documentation

## Project Overview

WayfindR-LLM is a comprehensive tour guide robot fleet management system that combines:

- **Robot Fleet Management**: Track, monitor, and control multiple autonomous tour guide robots
- **AI-Powered Interactions**: Natural language processing for both operators and visitors
- **Live Map Monitoring**: Real-time visualization of robot positions, zones, and waypoints
- **Telemetry Storage**: Vector-based telemetry storage (Qdrant) and conversation logging (PostgreSQL)

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           WayfindR-LLM Server                           │
│                         (FastAPI Application)                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │   Web Chat   │  │  Robot Chat  │  │  Telemetry   │  │  Map/Zones  │ │
│  │  (Operator)  │  │  (Visitors)  │  │   Handler    │  │   Handler   │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘ │
│         │                 │                 │                  │        │
│         └────────┬────────┴─────────────────┴──────────────────┘        │
│                  │                                                      │
│         ┌────────▼────────┐                                             │
│         │   LLM Engine    │                                             │
│         │  (Ollama/HPC)   │                                             │
│         │ llama3.3:70b    │                                             │
│         └────────┬────────┘                                             │
│                  │                                                      │
│    ┌─────────────┼─────────────┐                                        │
│    │             │             │                                        │
│    ▼             ▼             ▼                                        │
│ ┌──────┐    ┌──────────┐   ┌──────────┐                                │
│ │Qdrant│    │PostgreSQL│   │Map Config│                                │
│ │Vector│    │ Messages │   │  (JSON)  │                                │
│ │ Store│    │   Logs   │   │          │                                │
│ └──────┘    └──────────┘   └──────────┘                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
         ▲                    ▲                    ▲
         │                    │                    │
    ┌────┴────┐         ┌─────┴─────┐        ┌────┴────┐
    │ Robots  │         │  Android  │        │Operator │
    │(ROS 2 + │         │   App     │        │Dashboard│
    │ LiDAR)  │         │(Visitors) │        │  (Web)  │
    └─────────┘         └───────────┘        └─────────┘
```

## Key Components

### 1. Chat System (Dual Mode)

The system supports two distinct chat interfaces:

- **Operator Console** (`/chat`): For building staff to monitor and control robots
- **Robot Chat** (`/robot_chat`): For visitors interacting with robots via Android tablets

Each mode has its own system prompt and intent parsing to handle appropriate commands.

### 2. Telemetry System

Robots self-register by sending telemetry data. No manual registration required.

- Telemetry stored as vectors in Qdrant for similarity search
- Real-time status tracking (battery, location, status)
- Historical telemetry for trend analysis

### 3. Map & Zone Management

- **Multi-floor support**: Configure multiple building floors
- **Waypoints**: Define navigation destinations
- **Zones**: Blocked areas, priority paths, slow zones, restricted areas
- **Live updates**: Zones can be modified in real-time
- **Zone expiration**: Temporary zones with automatic expiration

### 4. LLM Integration

Uses Ollama with llama3.3:70b model (via HPC cluster) for:

- Intent parsing (understanding user requests)
- Response generation (natural language responses)
- Function execution (robot commands)

## Directory Structure

```
WayfindR-LLM/
├── main.py              # FastAPI application entry point
├── startup.py           # Server startup and configuration
├── llm_config.py        # Ollama/LLM configuration
├── requirements.txt     # Python dependencies
├── docker-compose.yml   # Docker services (Qdrant, PostgreSQL)
│
├── agents/              # LLM agent components
│   ├── intent_parser.py     # Parse user intents
│   ├── response_generator.py # Generate responses
│   ├── function_executor.py  # Execute robot commands
│   └── system_prompts.py     # System prompt templates
│
├── api/                 # API handlers
│   ├── chat_handler.py      # Chat endpoints
│   ├── telemetry_handler.py # Telemetry endpoints
│   ├── map_handler.py       # Map/zone endpoints
│   └── streaming.py         # SSE streaming endpoints
│
├── core/                # Core business logic
│   ├── config.py           # Application configuration
│   └── map_config.py       # Map data models and manager
│
├── rag/                 # Storage layer
│   ├── qdrant_store.py     # Qdrant vector storage
│   └── postgresql_store.py # PostgreSQL message storage
│
├── templates/           # HTML templates
│   ├── index.html          # Main dashboard
│   ├── diagnostics.html    # Robot diagnostics page
│   └── map.html            # Live map monitoring
│
├── static/              # Static assets
│   ├── css/               # Stylesheets
│   └── js/                # JavaScript files
│
├── data/                # Runtime data storage
│   └── map_config.json    # Persisted map configuration
│
├── docs/                # Documentation (this directory)
│
└── scripts/             # Utility scripts
```

## Quick Start

1. **Start Docker services**:
   ```bash
   docker-compose up -d
   ```

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Ollama** (if using local LLM):
   ```bash
   ./launch_ollama.sh
   ```

4. **Start the server**:
   ```bash
   python main.py
   ```

5. **Access the dashboard**:
   - Main dashboard: `http://localhost:8000`
   - Live map: `http://localhost:8000/map`
   - Robot diagnostics: `http://localhost:8000/diagnostics/{robot_id}`

## Documentation Index

- [Architecture](ARCHITECTURE.md) - Detailed system architecture
- [API Reference](API_REFERENCE.md) - Complete API endpoint documentation
- [Map System](MAP_SYSTEM.md) - Zone and waypoint management
- [Setup Guide](SETUP.md) - Installation and deployment

## Robot Integration

Robots integrate with WayfindR-LLM by:

1. **Sending telemetry** to `/telemetry` endpoint
2. **Querying map state** from `/map/state/{robot_id}`
3. **Receiving commands** via the chat system

See [API Reference](API_REFERENCE.md) for detailed endpoint specifications.

## Future Development

The system is designed to support:

- Multi-agent architectures (different robot types, different prompts)
- Multi-LLM configurations (different models for different tasks)
- Enhanced path planning with zone awareness
- Real-time video streaming from robots
- Voice interaction support
