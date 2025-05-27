# Hybrid LLM-Robot Integration System Overview

## System Architecture Components

1. **Android App Interface**
   - Sends user queries to ChatApp API endpoint
   - Receives and displays LLM responses
   - May show robot status/position when relevant

2. **Backend Services**
   - **ChatApp API**: Handles HTTP requests from mobile app
   - **PostgreSQL**: Stores conversation history with schema:
     - `user_id`, `timestamp`, `message_text`, `robot_context` (JSON)
   - **LLM Service**: Processes queries with RAG context
   - **Robot Telemetry Processor**: Aggregates sensor data

3. **Robot Systems**
   - Raspberry Pi with:
     - Local sensor processing
     - Basic navigation capabilities
     - Telemetry transmission
   - Qdrant database for:
     - Historical telemetry storage
     - Vector embeddings of navigation contexts

## Telemetry Handling Strategy

### Local Processing on Raspberry Pi
- **Raw Data Processed Onboard**:
  - LIDAR → obstacle detection flags
  - IMU → current orientation
  - Wheel encoders → distance traveled
  - Ultrasonic → collision warnings

- **Transmitted Telemetry**:
  ```json
  {
    "timestamp": "ISO-8601",
    "position": {"x": float, "y": float, "confidence": 0-1},
    "movement_state": {
      "speed": float,
      "distance_today": float,
      "status": ["moving","stopped","stuck","error"]
    },
    "environment": {
      "nearby_obstacles": int,
      "recent_collision": bool
    }
  }
  ```

### Qdrant Database Usage
- Stores telemetry snapshots at 1Hz frequency
- Maintains vector embeddings of:
  - Navigation waypoints
  - Common obstacle patterns
  - Historical navigation issues

## LLM Integration Design

### Model Context Protocol (MCP) Structure
1. **Conversation Context**:
   - Last 5 message exchanges
   - Current robot status summary
   - Building layout knowledge

2. **Function Calling Schema**:
  ```json
  {
    "name": "navigate",
    "description": "Direct robot to specified waypoint",
    "parameters": {
      "type": "object",
      "properties": {
        "waypoints": {
          "type": "array",
          "items": {"type": "string"},
          "description": "List of waypoint IDs in order"
        },
        "urgency": {
          "type": "string",
          "enum": ["normal", "urgent", "cautious"]
        }
      }
    }
  }
  ```

### RAG Implementation
1. **Context Retrieval**:
   - User query → vector embedding
   - Similarity search against:
     - Conversation history
     - Navigation documentation
     - Telemetry patterns
   - Top 3 relevant contexts injected into prompt

2. **Dynamic Prompt Structure**:
  ```
  [System] You are a robotic guide assistant. Current status: {robot_status}

  Recent context:
  - {context_point_1}
  - {context_point_2}

  Available functions: {function_list}

  User query: {query}
  ```

### LLM Coaching Strategy
1. **Navigation Intent Detection**:
   - Watch for keywords: "guide", "take me", "where is", "go to"
   - Confirm with user: "Would you like me to navigate to that location?"

2. **Function Call Generation**:
   - Required conditions:
     - Clear destination mentioned
     - Robot in operational state
     - No active obstacles
   - Error handling:
     - If stuck: "I'm currently having navigation difficulties. Please wait..."
     - If busy: "I'm currently assisting another guest..."

3. **Robot-Initiated Prompts**:
   - Automatic alerts trigger LLM function calls:
     - "Robot1 stuck at position X,Y. Requesting path recalculation"
     - "Low battery detected. Need to return to charging station"

## Workflow Examples

### User-Initiated Navigation
1. User: "Take me to the conference room"
2. LLM detects navigation intent
3. Checks telemetry for robot availability
4. Generates function call: `navigate(["conf_room"])`
5. Robot executes while sending periodic updates

### Robot-Initiated Recovery
1. Telemetry shows 5+ minutes without movement
2. System auto-generates prompt: "Navigation stuck near Way3"
3. LLM responds with function call: `navigate(["way3", "charging_station"], urgency="cautious")`
4. Robot attempts recovery path

## Implementation Recommendations

1. **Telemetry Sampling**:
   - Normal operation: 1Hz sampling
   - Error states: 5Hz sampling for 30 seconds

2. **Context Window Management**:
   - Keep last 3 telemetry snapshots in LLM context
   - Store 24h of telemetry in Qdrant
   - Archive older data to PostgreSQL

3. **Safety Considerations**:
   - Always verify navigation commands against current telemetry
   - Implement hardware emergency stop
   - Maintain manual override capability

4. **Performance Optimization**:
   - Pre-compute common waypoint routes
   - Cache frequent user queries
   - Use lightweight models for intent detection