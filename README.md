> [Mermaid for Markdown](https://github.com/mermaid-js/mermaid)

> using llama3.3:70b-instruct-q5_K_M

## Setup LightRAG `from source` locally

Make sure LightRAG is local (added as a submodule in CARS_SIM_2_OLLAMA)

```bash
git submodule update --init --recursive  
```

if want to update LightRAG submodule to use latest upstream LightRAG repo version: 

```bash
git submodule update --remote --recursive
```

Install LightRAG Core

```bash
cd demos/7-mature_RAG/LightRAG; pip install -e .
```

OR Install LightRAG Core + API

```bash
cd demos/7-mature_RAG/LightRAG; pip install -e ".[api]"
```

Some other dependencies
```bash
pip install wcwidth jwt aiofiles
```

### Run the Simulation and Chatapp

```
docker compose down -v; sudo chown -R $USER:$USER ./pg_data; sudo chown -R $USER:$USER ./qdrant_data; rm -rf ./pg_data ./qdrant_data; docker compose up -d; python sim.py
```

```
python3 mcp_chatapp.py
```

### Run the mini demo for LightRAG

download the demo document of "A Christmas Carol" by Charles Dickens

```bash
curl https://raw.githubusercontent.com/gusye1234/nano-graphrag/main/tests/mock_data.txt > ./demos/7-mature_RAG/7.1-mini_demo_LightRAG/book.txt
```

run the lightRAG mini demo code
```bash
python ./demos/7-mature_RAG/7.1-mini_demo_LightRAG/lightrag_demo_ollama.py
```

### Other Things For LightRAG & Ollama

it is important to note that the LightRAG Server will load the environment variables from .env into the system environment variables each time it starts. Since the LightRAG Server will prioritize the settings in the system environment variables, if you modify the .env file after starting the LightRAG Server via the command line, you need to execute source .env to make the new settings take effect.

By default, Ollama operates with a context window size of 2048 tokens, which can be adjusted to better suit your needs. 

For example, to set the context size to 8000 tokens: 
Code

ollama run llama3 --num_ctx 8000

ollama run llama3.3:70b-instruct-q5_K_M --num_ctx 8000


The LightRAG Server supports two operational modes:

The simple and efficient Uvicorn mode:

```bash
lightrag-server
```

The multiprocess Gunicorn + Uvicorn mode (production mode, not supported on Windows environments):

```bash
lightrag-gunicorn --workers 4
```

The .env file must be placed in the startup directory.


Here are some commonly used startup parameters:

    --host: Server listening address (default: 0.0.0.0)
    --port: Server listening port (default: 9621)
    --timeout: LLM request timeout (default: 150 seconds)
    --log-level: Logging level (default: INFO)
    --input-dir: Specifying the directory to scan for documents (default: ./inputs)


# updating ollama models locally on VEGA HPC
 - stop ollama serve on gpu, start ollama serve on vega, then pull models
 - ollama pull gemma:2b
 - ollama pull nomic-embed-text
 - then go back to ollama serve on gpus