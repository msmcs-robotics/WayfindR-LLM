# Indoor Navigation Robot - Implementation Guide

## System Overview

This guide outlines building an autonomous indoor navigation robot with three integrated systems:

### 1. **Raspberry Pi Robot Controller**
- **Hardware**: RP LIDAR A1, L298N motor driver, 4-wheel skid-steer system, HC-SR04 ultrasonic sensors
- **Function**: SLAM mapping, localization, path planning, obstacle avoidance, motor control
- **Communication**: Runs Flask server to receive navigation commands via HTTP

### 2. **Linux Backend Server (FastAPI + LLM)**
- **Components**: FastAPI web server, Ollama with local LLaMA model, Model Context Protocol (MCP)
- **Function**: Processes user queries, interprets navigation requests, sends movement commands to robot
- **LLM Integration**: Uses Ollama for local LLM inference (avoiding cloud dependencies)

### 3. **Android Tablet Interface**
- **Hardware**: Samsung Galaxy A9 tablet as user interface
- **Function**: Voice input (speech-to-text), text display in chat UI, audio output (text-to-speech)
- **Communication**: HTTP requests to backend server over WiFi

## System Architecture & Data Flow

```
[User Voice Input] → [Android STT] → [HTTP to Backend] → [LLM Processing] 
                                                              ↓
[Android TTS] ← [HTTP Response] ← [Function Calls] → [Commands to Pi] → [Robot Movement]
```

1. User speaks to Android tablet
2. Android converts speech to text and sends to backend
3. Backend LLM processes request and generates navigation commands
4. Backend sends movement commands to Raspberry Pi
5. Pi executes navigation using SLAM map and motor control
6. Response flows back to Android for display and speech output

## Implementation Steps

### Phase 1: Hardware Setup

1. **Assemble Robot Hardware**
   - Mount RP LIDAR A1 on robot chassis
   - Connect L298N motor driver to 4 DC motors (2 left, 2 right wheels)
   - Wire ultrasonic sensors for obstacle detection
   - Connect all components to Raspberry Pi GPIO pins

2. **Network Configuration**
   - Ensure all devices (Pi, Android, Backend server) on same WiFi network
   - Configure static IPs or use hostname resolution

### Phase 2: Raspberry Pi Robot System

3. **Install Dependencies**
   ```bash
   pip3 install adafruit-circuitpython-rplidar flask numpy RPi.GPIO
   ```

4. **Implement SLAM Mapping**
   - Create occupancy grid mapper using LIDAR data
   - Build map by manually driving robot around building
   - Save map and define waypoints for rooms/locations

5. **Motor Control System**
   - Implement skid-steer driving functions (forward, backward, turn left/right)
   - Add obstacle avoidance using ultrasonic sensors
   - Create path planning with A* algorithm on occupancy grid

6. **Command Server**
   - Flask server listening on port 5000
   - Accepts JSON commands: `{"action": "goto", "dest": "kitchen"}`
   - Executes navigation to waypoints using SLAM map

### Phase 3: Backend LLM Server

7. **Install Ollama and Dependencies**
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull llama3.1:13b
   pip install flask langchain-ollama requests
   ```

8. **Create FastAPI Application**
   - HTTP endpoint `/query` accepting user text
   - LLM prompt engineering for navigation commands
   - Function calling to translate user intent to robot commands
   - Forward navigation requests to Raspberry Pi

9. **Model Context Protocol Integration**
   - Parse LLM responses for function calls
   - Map natural language to specific robot actions
   - Handle error responses and status updates

### Phase 4: Android Application

10. **Setup Android Project**
    - Create Kotlin project with required permissions (INTERNET, RECORD_AUDIO)
    - Add OkHttp dependency for HTTP requests

11. **Implement Voice Interface**
    - Use Android's built-in SpeechRecognizer for voice input
    - Create chat UI with RecyclerView for conversation history
    - Implement TextToSpeech for audio responses

12. **Network Communication**
    - HTTP client to send text queries to backend
    - JSON parsing for LLM responses
    - Error handling and connection management

### Phase 5: Integration & Testing

13. **System Integration**
    - Test communication between all three components
    - Verify SLAM mapping accuracy and navigation
    - Tune LLM prompts for reliable function calling

14. **Field Testing**
    - Test end-to-end user scenarios
    - Calibrate obstacle avoidance sensitivity
    - Optimize path planning for building layout

15. **Deployment**
    - Configure services to start on boot
    - Implement logging and error recovery
    - Create user documentation and safety protocols

## Key Technologies Used

- **SLAM**: Custom occupancy grid mapping with RP LIDAR A1
- **LLM**: Local LLaMA model via Ollama for offline operation
- **Communication**: HTTP/REST APIs over WiFi
- **Hardware Control**: RPi.GPIO for motor drivers and sensors
- **Voice Processing**: Android native STT/TTS (no cloud APIs)
- **Path Planning**: A* algorithm on occupancy grid

## Expected Capabilities

- Voice-controlled navigation to named locations
- Real-time obstacle avoidance during movement
- Conversational interface with natural language understanding
- Autonomous return to home base after task completion
- Offline operation (no internet required for core functions)