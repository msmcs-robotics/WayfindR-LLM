#!/bin/bash
# Automates Ollama service/model on GPU via jump host
# For WayfindR-LLM Tour Guide Robot System

set -euo pipefail

# --- CONFIG ---
JUMP_HOST="ERAUUSER@vegaln1.erau.edu"
GPU_HOST="ERAUUSER@gpu02"
VEGA_HOST="ERAUUSER@vegaln1.erau.edu"
LOCAL_PORT=11434
REMOTE_PORT=REMOTEPORT
OLLAMA_BIN="/home2/ERAUUSER/.local/bin/ollama/bin/ollama"

ACTION="start"
VERBOSE=0

# --- HELPER FUNCTIONS ---
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

OPTIONS:
    --stop          Stop ollama serve and port forward
    --status        Show status of Ollama service
    --list          List available models
    --verbose       Enable verbose debug output
    -h, --help      Show this help message

EXAMPLES:
    $0                           # Start serve + port forward
    $0 --status                  # Check status
    $0 --list                    # List available models
    $0 --stop                    # Stop everything

HOW IT WORKS:
    - Starts 'ollama serve' on GPU
    - Models are loaded automatically on first API request
    - Check which models are currently loaded in memory with --status
EOF
}

# Execute command on GPU via jump host
run_on_gpu() {
    if [ "${VERBOSE:-0}" = "1" ]; then
        echo "  [GPU] Running: $*" >&2
    fi
    ssh -o ConnectTimeout=10 -J "$JUMP_HOST" "$GPU_HOST" "$@"
}

# Check if ollama serve is running on GPU
is_ollama_running() {
    local count
    count=$(run_on_gpu "ps aux | grep '[o]llama serve' | grep -v grep | wc -l")
    if [ "$count" -gt 0 ]; then
        echo "yes"
    else
        echo "no"
    fi
}

# Get PID of ollama serve
get_ollama_pid() {
    run_on_gpu "ps aux | grep '[o]llama serve' | grep -v grep | awk '{print \$2}' | head -1"
}

# Get all loaded model processes (models currently in memory)
get_loaded_models() {
    local all_pids=$(run_on_gpu "pgrep -f 'ollama runner' 2>/dev/null || true")

    if [ -z "$all_pids" ]; then
        return
    fi

    for pid in $all_pids; do
        local ppid=$(run_on_gpu "ps -o ppid= -p $pid 2>/dev/null | tr -d ' '")

        if [ -n "$ppid" ]; then
            local cmdline=$(run_on_gpu "ps -o args= -p $ppid 2>/dev/null || true")

            if echo "$cmdline" | grep -q "ollama"; then
                local model=$(echo "$cmdline" | grep -oP '(?<=model=)[^ ]+' || echo "unknown")
                if [ "$model" != "unknown" ]; then
                    echo "$pid $model"
                fi
            fi
        fi
    done
}

# Start ollama serve on GPU
start_ollama_serve() {
    if [ "$(is_ollama_running)" = "yes" ]; then
        echo "Ollama serve already running (PID: $(get_ollama_pid))"
        return 0
    fi

    echo "Starting ollama serve on GPU..."

    run_on_gpu "nohup bash -c 'OLLAMA_HOST=127.0.0.1:$REMOTE_PORT $OLLAMA_BIN serve > /tmp/ollama_serve.log 2>&1' >/dev/null 2>&1 & disown"

    echo "  Waiting for service to start..."
    sleep 3

    if [ "$(is_ollama_running)" = "yes" ]; then
        echo "Ollama serve started (PID: $(get_ollama_pid))"
    else
        echo "Failed to start ollama serve"
        echo ""
        echo "Diagnostics:"
        echo "  Checking log file..."
        run_on_gpu "tail -20 /tmp/ollama_serve.log 2>/dev/null || echo 'No log file found'"
        echo ""
        return 1
    fi
}

# Stop all ollama processes
stop_all() {
    echo "Stopping all Ollama processes..."

    local serve_pid
    serve_pid=$(get_ollama_pid)

    if [ -n "$serve_pid" ]; then
        echo "  Stopping ollama serve: $serve_pid"
        run_on_gpu "kill $serve_pid 2>/dev/null || true"
    fi

    if [ -z "$serve_pid" ]; then
        echo "  No ollama processes found on GPU"
    fi

    sleep 1

    if lsof -ti:$LOCAL_PORT >/dev/null 2>&1; then
        echo "  Stopping local port forward..."
        kill $(lsof -ti:$LOCAL_PORT) 2>/dev/null || true
    fi

    echo "All processes stopped"
}

# Show status
show_status() {
    echo "==================================="
    echo "OLLAMA STATUS"
    echo "==================================="

    echo -e "\n--- Ollama Service (GPU) ---"
    if [ "$(is_ollama_running)" = "yes" ]; then
        local pid
        pid=$(get_ollama_pid)
        echo "Status: RUNNING"
        echo "PID: $pid"
        echo "Port: $REMOTE_PORT"
    else
        echo "Status: NOT RUNNING"
    fi

    echo -e "\n--- Currently Loaded Models (in memory) ---"
    if [ "$(is_ollama_running)" = "yes" ]; then
        local loaded_models
        loaded_models=$(get_loaded_models)

        if [ -z "$loaded_models" ]; then
            echo "No models currently loaded in memory"
            echo "(Models load automatically on first API request)"
        else
            local index=1
            while IFS= read -r line; do
                if [ -n "$line" ]; then
                    local pid=$(echo "$line" | awk '{print $1}')
                    local model_name=$(echo "$line" | awk '{print $2}')
                    echo "[$index] $model_name (PID: $pid)"
                    ((index++))
                fi
            done <<< "$loaded_models"
        fi
    else
        echo "(Ollama serve not running)"
    fi

    echo -e "\n--- Available Models ---"
    if [ "$(is_ollama_running)" = "yes" ]; then
        run_on_gpu "OLLAMA_HOST=127.0.0.1:$REMOTE_PORT $OLLAMA_BIN list 2>/dev/null"
    else
        echo "(Ollama serve not running)"
    fi

    echo -e "\n--- Local Port Forward ---"
    if lsof -ti:$LOCAL_PORT >/dev/null 2>&1; then
        echo "Status: ACTIVE"
        echo "Local: localhost:$LOCAL_PORT -> GPU:$REMOTE_PORT"
        echo "PID: $(lsof -ti:$LOCAL_PORT)"
    else
        echo "Status: NOT ACTIVE"
    fi
    echo "==================================="
}

# List available models
list_models() {
    echo "==================================="
    echo "AVAILABLE MODELS"
    echo "==================================="

    if [ "$(is_ollama_running)" != "yes" ]; then
        echo "Error: Ollama serve is not running"
        echo "Start it first with: $0"
        return 1
    fi

    echo ""
    run_on_gpu "OLLAMA_HOST=127.0.0.1:$REMOTE_PORT $OLLAMA_BIN list 2>/dev/null"
    echo ""
    echo "==================================="
}

# Setup port forwarding
setup_port_forward() {
    if lsof -ti:$LOCAL_PORT >/dev/null 2>&1; then
        echo "Port forward already active, keeping existing connection"
        return 0
    fi

    echo "Setting up port forward: localhost:$LOCAL_PORT -> GPU:$REMOTE_PORT"
    ssh -f -N -L "$LOCAL_PORT:127.0.0.1:$REMOTE_PORT" -J "$JUMP_HOST" "$GPU_HOST"
    sleep 1

    if lsof -ti:$LOCAL_PORT >/dev/null 2>&1; then
        echo "Port forward established"
    else
        echo "Failed to establish port forward"
        return 1
    fi
}

# --- ARGUMENT PARSING ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --stop)
            ACTION="stop"
            shift
            ;;
        --status)
            ACTION="status"
            shift
            ;;
        --list)
            ACTION="list"
            shift
            ;;
        --verbose|-v)
            VERBOSE=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Error: Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# --- MAIN ---
case $ACTION in
    start)
        echo "Starting Ollama Service"
        echo "-----------------------------------"
        start_ollama_serve
        setup_port_forward
        echo "-----------------------------------"
        echo "Setup complete!"
        echo "  Connect locally at: http://localhost:$LOCAL_PORT"
        echo "  Models will load automatically on first API request"
        echo ""
        echo "Commands:"
        echo "  ./launch_ollama.sh --status    # Check status + loaded models"
        echo "  ./launch_ollama.sh --list      # List available models"
        echo "  ./launch_ollama.sh --stop      # Stop everything"
        ;;
    stop)
        stop_all
        ;;
    status)
        show_status
        ;;
    list)
        list_models
        ;;
esac
