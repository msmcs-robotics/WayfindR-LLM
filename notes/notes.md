```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.11 python3.11-venv
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

```bash
docker compose down -v; docker compose up -d; python3 main_mcp.py
```


basically i want you to condense the attatched code without losing the core functionality:

I am trying to make a backend linux server that wil run an LLM to help interpret what is going on to enable a robot that greets people and provides guidance through a building. I will have an android app that interfaces with a user and sends user input in hte form of a string to a chatapp api url and then those chat messages will be stored in postgresql. i then have a raspberry pi that will collect telemetry from the robot's sensors such as lidar, and MPU, and wheel encoders. the raspberry pi will perform simple calculations onboard to provide better context in the telemetry such as the following:
 - getting movement speed from IMU data
- expected position (x,y) from lidar
- expected distance traveled from wheel encoders
- timestamp from robot
this modified telemetry will be sent to an endpoint of the chatapp that then forwards it to the qdrant database using the RAG handler. i want to make sure that the chatapp can handle this telemetry data and store it in the qdrant database, while also being able to retrieve it for context in conversations.
I have split my mcp chatapp into multiple files, one is the main mcp app with all the api endpoints, another file is the chat handler for storing chat messages and retirieving chat messages from postgresql (should be delegated to RAG) and then the third is the telemetry handler where telemetry is sent to the endpoint at the main mcp app then that data should be handled using the telemetry handler then send to RAG. the chat handler should use RAG to pull data from postgres and qdrant. the telemetry handler simply recieves telemetry data passed from the mcp app that recieved it on an endpoint, then if other endpoints for telemetry are accessed, the telemetry handler will handle it and use RAG to pull data from the database if needed. please make these files more cohesive and refactor the code to not be redundant and make things flow better. you don't need to give me the complete files but please point out where to make improvements in what files and the improved code.

for clarity, all things in postgresql are not supposed to be vectored, but rather normal postgresql entries for the chat messages, then qdrant is supposed to be vector storage of telemetry points.