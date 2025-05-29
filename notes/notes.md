**Setup python 3.11 virtual environment:**

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.11 python3.11-venv
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Install Docker & Docker Compose:**

```bash
sudo apt install -y docker.io; sudo groupadd docker; sudo usermod -aG docker $USER; sudo systemctl start docker; sudo systemctl enable docker; newgrp docker
```bash

```bash
DOCKER_CONFIG=${DOCKER_CONFIG:-$HOME/.docker}; mkdir -p $DOCKER_CONFIG/cli-plugins; curl -SL https://github.com/docker/compose/releases/download/v2.35.0/docker-compose-linux-x86_64 -o $DOCKER_CONFIG/cli-plugins/docker-compose; chmod +x $DOCKER_CONFIG/cli-plugins/docker-compose; docker compose version
```

**Run the docker images and start the app:**

```bash
docker compose down -v; sudo chown -R $USER:$USER ./pg_data ./qdrant_data; rm -rf ./pg_data ./qdrant_data; docker compose up -d; python3 main_mcp.py
```

**Remove items not kept in git, except the venv**

```bash
git clean -xdn -e venv/
git clean -xdf -e venv/
```



some prompts used along the way:





I have the following FastAPI mcp system with RAG and a hybrid storage solution that aims to use an LLM to provide high level overviews of a robot navigating autonomously through a chat interface. I want to remove redundant code and make things more streamlined. I have endpoints for user chat messages through the chat webapp, endpoints for chat messages from robots (that users send through an android app), and endpoints for telemetry data from the robot. Telemetry is stored in qdrant and messages are stored in postgresql. I want to make sure i am keeping track of which messages are attatched to which conversation, and which conversation is attached to what web user or robot (user on robot but just use the robot id or something to make it simple).

While it is nice to have the LLM be able to provide guidance to robots when they are reporting as stuck, in reality the LLM should not assist in navigation but rather make a function call to an alert system for humans, please only make a simple "empty" alert function that can be called when the robot is stuck, but do not implement any actual alerting system. This feature should encompass the LLM assistance for stuck robots. The robots themselves will be equipped with navigation and decision-making capabilities for movement and waypoint navigation, so the LLM should not be involved in that aspect. The LLM simply provides high-level overviews and context for the robot's actions and interactions with users, then be able to handle small talk with users using robots. However, while the llm doesn't tell the robot how to navigate, I want to have functionality where the LLM interprets if the user of a robot needs to be taken somewhere, and then the LLM should make a function call to the robot to navigate to a specific location, but this should be a simple function call that does not involve any complex navigation logic. The LLM should simply provide the high-level overview and context for the robot's actions and interactions with users. The LLM simply deciphers what waypoints the user wants to go to and then makes a function call to the robot to navigate to that waypoint, but the actual navigation logic should be handled by the robot itself. If it is multiple waypoints, the LLM should simply make a function call to the robot to navigate though the list of waypoints, the robot will be able to decide onboard how to optimize the path and navigate through the waypoints.

i want to async search for all existing robot IDs/names and send this uniqe list to the LLM so it can use this context to identify which robot is being mentioned in the chat messages. Ideally i would want an async function to keep track of existing robots in the system based on all existing uniqe robot names/ids in the qdrant telemetry database every minute. this way i am not having to always search the database everytim i prompt the LLM. I want to make sure that the LLM can effectively understand and provide context for the robot's actions and interactions with users, and that it can handle small talk with users using robots through the robot chat. Be aware that the frontend javascript and html are perfectly functioning and all they do is send and receive data from the FastAPI backend, so you do not need to modify any frontend code, but make sure that the backend is cohesive and not redundant, and that it flows well together.

I want to update the main component of my app to include these new features and ensure that the code is modular, cohesive, and not redundant. Please point out where to make improvements in what files and provide improved code snippets.

Please point out where to make improvements in what files and provide improved code snippets.

 
Given the following goals and constraints, My web chat using index.html and script.js does not properly communicate with my backend. I need to be able to send web chats through the web chat itself, but maintain log streaming from databases. Also please point out where to make improvements in what files and provide improved code snippets that affect overall modulariry, cohesiveness, and not-redundancy of code.
##  Goals
### Core Functionality
-  Use LLM to provide **high-level overviews** of robot activity via a chat interface.
-  Support **small talk** between web users and robots via chat.
-  **Do not** allow the LLM to assist with navigation or decision-making for movement.
### Chat System
-  Maintain **separate chat endpoints** for:
  - `/web_chat/`: Handles messages from web users.
  - `/robot_chat/`: Handles messages from robot-side users (e.g. Android app).
-  Track chat metadata:
  - `conversation_id`: Links a series of messages together.
  - `user_id` or `robot_id`: Associates a conversation with a human or a robot.
### FastAPI Port 5000 Frontend
-  Simply sends and receives data from the FastAPI backend.
-  Handles chat messages and streams telemetry data.
-  No modifications needed to the frontend code.
### LLM Capabilities
-  **Stuck Robot Handling**:
  - LLM detects when a robot is stuck.
  - LLM makes a call to `alert_humans(robot_id)` (a stub function; no actual alerting logic).
-  **Waypoint Navigation Requests**:
  - LLM interprets user intent (e.g., “Take me to the lab”).
  - Calls `navigate_to_waypoint(robot_id, waypoints: list[str])`.
  - Robot handles all navigation internally (LLM only passes the waypoints).
### Data Storage
-  Use hybrid storage:
  - **Telemetry** data in **Qdrant**.
  - **Chat** messages in **PostgreSQL**.
-  Link data via metadata (e.g., robot_id, conversation_id).
### Robot Context Management
-  Maintain **cached list of robot names/IDs** for LLM context.
  - Refresh every **60 seconds** asynchronously from Qdrant.
  - Avoid querying Qdrant on every LLM prompt.
-  Use this context to help LLM **identify which robot** is being referenced in a chat.
### Code Quality & Architecture
-  **Modularize** all components:
  - Clear separation of chat, telemetry, and LLM logic.
  - No repeated logic or code redundancy.
-  Keep **frontend untouched**:
  - All API contracts should remain the same for compatibility with existing HTML/JS.
  - Backend-only improvements.
##  Constraints
### No LLM Navigation Logic
-  LLM **must not** plan robot paths or routes.
-  LLM only forwards waypoints to the robot using `navigate_to_waypoint(...)`.
### No Real Alerts
-  Do not implement any full alerting system.
-  Use a placeholder: `alert_humans(robot_id)` that just logs or returns a stub response.
### Minimize Database Load
-  Cache robot list from Qdrant **once per minute** asynchronously.
-  Do not query the telemetry DB every time the LLM is prompted.
### Endpoint Separation
-  `/web_chat/` handles web user messages.
  - gives high level overviews regarding robot activity. leverages active robots list for LLM to then make a request for which robots to get context on.
-  `/robot_chat/` handles messages from the robot-side user.
  - simply provides small talk for a user being greeted by a robot in person and leverages the LLM to understand user needs like navigation to a waypoint.
### Two-Phase LLM Strategy
- Instead of hardcoded parsing, use:
 - Phase 1: LLM analyzes the message and returns structured JSON with function calls and robot mentions
 - Phase 2: LLM generates the actual response using the parsed context
- I don't want to hardcode message parsing to understand what functions are being called or what robots are being mentiond. Rather i want to send a message to the LLM and have the LLM figure out what functions are being called and what robots are being mentioned. From this response the MCP should then take that list of functions being called and list of robots being mentioned and ask the LLM to provide a complete response given the chat message. From here the LLM should be able to give specific details on what information goes into what function call


