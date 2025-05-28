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


basically i want you to condense the attatched code without losing the core functionality:

I am trying to make a backend linux server that wil run an LLM to help interpret what is going on to enable a robot that greets people and provides guidance through a building. I will have an android app that interfaces with a user and sends user input in hte form of a string to a chatapp api url and then those chat messages will be stored in postgresql. i then have a raspberry pi that will collect telemetry from the robot's sensors such as lidar, and MPU, and wheel encoders. the raspberry pi will perform simple calculations onboard to provide better context in the telemetry such as the following:
 - getting movement speed from IMU data
- expected position (x,y) from lidar
- expected distance traveled from wheel encoders
- timestamp from robot
this modified telemetry will be sent to an endpoint of the chatapp that then forwards it to the qdrant database using the RAG handler. i want to make sure that the chatapp can handle this telemetry data and store it in the qdrant database, while also being able to retrieve it for context in conversations.
I have split my mcp chatapp into multiple files, one is the main mcp app with all the api endpoints, another file is the chat handler for storing chat messages and retirieving chat messages from postgresql (should be delegated to RAG) and then the third is the telemetry handler where telemetry is sent to the endpoint at the main mcp app then that data should be handled using the telemetry handler then send to RAG. the chat handler should use RAG to pull data from postgres and qdrant. the telemetry handler simply recieves telemetry data passed from the mcp app that recieved it on an endpoint, then if other endpoints for telemetry are accessed, the telemetry handler will handle it and use RAG to pull data from the database if needed. please make these files more cohesive and refactor the code to not be redundant and make things flow better. you don't need to give me the complete files but please point out where to make improvements in what files and the improved code.

for clarity, all things in postgresql are not supposed to be vectored, but rather normal postgresql entries for the chat messages, then qdrant is supposed to be vector storage of telemetry points.




I have the following FastAPI mcp system with RAG and a hybrid storage solution that aims to use an LLM to provide high level overviews of a robot navigating autonomously through a chat interface. I have endpoints for user chat messages through the chat app and telemetry data from the robot. however since i am making greeting robots, I want to add an endpoint and prompt for chat messages from the robots, its not that robots will be chatting with the LLM but i want to also leverage the LLM to handle "small talk" or conversations with users that are directrly communicating with the robots through an android tablet. I have already build and configured the android app to send chat messages to the chat app api url, but now I need to add the endpoint for the robot's chat messages. I want to make sure that the robot's chat messages are stored in postgresql and can be retrieved using RAG for context in conversations. I also want to make sure that the robot's telemetry data is sent to the telemetry handler and stored in qdrant for vector storage. I have already built the main mcp app with all the api endpoints, a chat handler for storing and retrieving chat messages from postgresql, and a telemetry handler for handling telemetry data. I want to make sure that these components are cohesive and not redundant, and that they flow well together. Please create a new "robot_chat_handler_mcp.py" file that will handle the robot's chat messages and integrate it with the existing chat handler and telemetry handler. The new file should have endpoints for receiving robot chat messages, storing them in postgresql, and retrieving them using RAG for context in such conversations. The robot's telemetry data should also be sent to the telemetry handler and stored in qdrant for vector storage. Please keep track of which messages are attatched to which conversation and which conversation is attatched to a user on the frontend or a robot. use chat_handler_mcp.py and telemetry_handler_mcp.py as references for the new file. The new file should be cohesive with the existing handlers and not redundant.

Please point out where to make improvements in what files and provide improved code snippets.



I have the following FastAPI mcp system with RAG and a hybrid storage solution that aims to use an LLM to provide high level overviews of a robot navigating autonomously through a chat interface. I want to remove redundant code and make things more streamlined. I have endpoints for user chat messages through the chat webapp, endpoints for chat messages from robots (that users send through an android app), and endpoints for  telemetry data from the robot. Telemetry is stored in qdrant and messages are stored in postgresql. I want to make sure i am keeping track of which messages are attatched to which conversation, and which conversation is attached to what web user or  robot (user on robot but just use the robot id or something to make it simple). 

While it is nice to have the LLM be able to provide guidance to robots when they are reporting as stuck, in reality the LLM should not assist in navigation but rather make a function call to an alert system for humans, please only make a simple "empty" alert function that can be called when the robot is stuck, but do not implement any actual alerting system. This feature should encompass the LLM assistance for stuck robots. The robots themselves will be equipped with navigation and decision-making capabilities for movement and waypoint navigation, so the LLM should not be involved in that aspect. The LLM simply provides high-level overviews and context for the robot's actions and interactions with users, then be able to handle small talk with users using robots.


i want to remove redundant code and make things more cohesive while maintaining the core functionality, simplicity, and modularity. I also want to remove any extra features that are non essential to the goals i just listed. Please point out where to make improvements in what files and provide improved code snippets.

Do not worry about the rag_store script for now as i will update it later. I want to get my data flowing and working first, then I will update the rag_store script to handle the data flow properly.









I have the following FastAPI mcp system with RAG and a hybrid storage solution that aims to use an LLM to provide high level overviews of a robot navigating autonomously through a chat interface. I want to remove redundant code and make things more streamlined. I have endpoints for user chat messages through the chat webapp, endpoints for chat messages from robots (that users send through an android app), and endpoints for telemetry data from the robot. Telemetry is stored in qdrant and messages are stored in postgresql. I want to make sure i am keeping track of which messages are attatched to which conversation, and which conversation is attached to what web user or robot (user on robot but just use the robot id or something to make it simple).

While it is nice to have the LLM be able to provide guidance to robots when they are reporting as stuck, in reality the LLM should not assist in navigation but rather make a function call to an alert system for humans, please only make a simple "empty" alert function that can be called when the robot is stuck, but do not implement any actual alerting system. This feature should encompass the LLM assistance for stuck robots. The robots themselves will be equipped with navigation and decision-making capabilities for movement and waypoint navigation, so the LLM should not be involved in that aspect. The LLM simply provides high-level overviews and context for the robot's actions and interactions with users, then be able to handle small talk with users using robots. However, while the llm doesn't tell the robot how to navigate, I want to have functionality where the LLM interprets if the user of a robot needs to be taken somewhere, and then the LLM should make a function call to the robot to navigate to a specific location, but this should be a simple function call that does not involve any complex navigation logic. The LLM should simply provide the high-level overview and context for the robot's actions and interactions with users. The LLM simply deciphers what waypoints the user wants to go to and then makes a function call to the robot to navigate to that waypoint, but the actual navigation logic should be handled by the robot itself. If it is multiple waypoints, the LLM should simply make a function call to the robot to navigate though the list of waypoints, the robot will be able to decide onboard how to optimize the path and navigate through the waypoints.

i want to remove redundant code and make things more cohesive while maintaining the core functionality, simplicity, and modularity. I also want to remove any extra features that are non essential to the goals i just listed. Please point out where to make improvements in what files and provide improved code snippets.


Do not worry about the rag_store script for now as i will update it later. I want to get my data flowing and working first, then I will update the rag_store script to handle the data flow properly.







I have the following FastAPI mcp system with RAG and a hybrid storage solution that aims to use an LLM to provide high level overviews of a robot navigating autonomously through a chat interface. I want to remove redundant code and make things more streamlined. I have endpoints for user chat messages through the chat webapp, endpoints for chat messages from robots (that users send through an android app), and endpoints for telemetry data from the robot. Telemetry is stored in qdrant and messages are stored in postgresql. I want to make sure i am keeping track of which messages are attatched to which conversation, and which conversation is attached to what web user or robot (user on robot but just use the robot id or something to make it simple).

While it is nice to have the LLM be able to provide guidance to robots when they are reporting as stuck, in reality the LLM should not assist in navigation but rather make a function call to an alert system for humans, please only make a simple "empty" alert function that can be called when the robot is stuck, but do not implement any actual alerting system. This feature should encompass the LLM assistance for stuck robots. The robots themselves will be equipped with navigation and decision-making capabilities for movement and waypoint navigation, so the LLM should not be involved in that aspect. The LLM simply provides high-level overviews and context for the robot's actions and interactions with users, then be able to handle small talk with users using robots. However, while the llm doesn't tell the robot how to navigate, I want to have functionality where the LLM interprets if the user of a robot needs to be taken somewhere, and then the LLM should make a function call to the robot to navigate to a specific location, but this should be a simple function call that does not involve any complex navigation logic. The LLM should simply provide the high-level overview and context for the robot's actions and interactions with users. The LLM simply deciphers what waypoints the user wants to go to and then makes a function call to the robot to navigate to that waypoint, but the actual navigation logic should be handled by the robot itself. If it is multiple waypoints, the LLM should simply make a function call to the robot to navigate though the list of waypoints, the robot will be able to decide onboard how to optimize the path and navigate through the waypoints.

my webapp effectively streams logs from the qdrant and postgresql databases, however from the web chat app the LLM does not seem to be able to get good context for a mentioned robot, i have provided some sample messages and telemetry data below. please improve the context building and prompting for the LLM to better understand the robot's state and actions based on the chat messages and telemetry data for the web user. I want to clarify that chat messages from robots themselves should still be handled as a separate entity and not mixed with the web user chat messages, but the LLM should be able to understand the context of the robot's state and actions based on the telemetry data and chat messages from the web user.

Please point out where to make improvements in what files and provide improved code snippets.

 