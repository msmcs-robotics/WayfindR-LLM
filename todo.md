OK great so this app is actually gonna work in conjunction with the Wayfinder driver app that you can see on the local system  ~/WayfindR-driver

Now I want to start testing the LLM app on a remote system that you'll be able to connect to if you read connections.Md. And if you read through wayfinder driver you'll see that I'm just simply testing it on this remote system it's not a Raspberry Pi it's just a normal Ubuntu system and I've connected the lidar through the USB and have tried to start making maps. And you should be able to see where it's trying to make the map so I'd like to be able to test the live streaming or live viewing of the map in this LLM app because it's not like the map is gonna be updating All robots should be using the same maps to navigate and if I so choose I'll update like the master map or something so really this LLM app just shows this map live in the browser and then it collects telemetry from various robots to be able to plot where robots would be on the map does this all make sense? So this should allow you to be able to more thoroughly test the current app that you're developing and also I wanted to mention how are you gonna get all this code onto the remote system well if you use rsync and then the folder I want you to copy it to might already exist but it's gonna be on the remote system ~/Desktop/WayfindR-LLM

Does this all make sense and the remote system you should be able to use the launcho llama scripts just the same I should have my VPN up and running on that remote system so you can run everything just the same as if you were running on this system it's just you have better access to information over there.


so docker is installed on that system and should already be set up please don't use anything other than docker for that storage and then also please use a Python virtual environment to install packages in just to clarify
















Wait a second is sentence transformers being used for embedding all messages being streamed for telemetry or something? Because Cudrant should be storing all forms of telemetry being collected on the endpoints and I'll have to update what exactly telemetry is being collected so don't worry about this And then Ostgreql should be storing all kind of the relational data like all the messages between everything. Just to clarify I don't want to be removing any functionality right now I'm just was curious as to why sentence transformer was was even needed because Olama should be handling enough We should just really be pushing everything into rag itself.


OK no I wanna be able to use semantic search but there should be an embedding model available through O Lama and already available on HPC system that I already polled. Would this make sense? 

https://ollama.com/library/all-minilm:l6-v2

Or is this not the same thing



These are tasks that you have previously set up in the past and different conversations and I want you to make sure that they are all completed and if not then complete them.



Update qdrant_store to use Ollama embeddings

Update postgresql_store to use Ollama embeddings

Add embedding model config to llm_config.py

Rsync and test on remote system