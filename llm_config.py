"""
LLM Configuration for WayfindR-LLM
Manages Ollama client connection with proper error handling
"""
import ollama
import time
from typing import Optional, Tuple

# Ollama configuration - connects through SSH tunnel
OLLAMA_HOST = "http://localhost:11434"  # Local end of SSH tunnel
LLM_MODEL = "llama3.3:70b-instruct-q5_K_M"
CONNECTION_TIMEOUT = 30  # Increased for model loading
MAX_RETRIES = 3


def get_ollama_client():
    """Get configured Ollama client"""
    return ollama.Client(host=OLLAMA_HOST)


def get_model_name():
    """Get the LLM model name"""
    return LLM_MODEL


def test_ollama_connection(client=None, verbose=True) -> bool:
    """Test if Ollama is accessible and model exists"""
    if client is None:
        client = get_ollama_client()

    try:
        if verbose:
            print(f"[LLM] Testing connection to {OLLAMA_HOST}...")

        # Try to list models
        models = client.list()

        if verbose:
            print(f"[LLM] Connected successfully")
            model_list = [m.get('name', m.get('model', 'unknown')) for m in models.get('models', [])]
            print(f"[LLM] Available models: {model_list}")

        # Check if our model is available
        model_names = [m.get('name', m.get('model', '')) for m in models.get('models', [])]

        model_found = False
        for name in model_names:
            if LLM_MODEL in name or name in LLM_MODEL:
                model_found = True
                if verbose and name != LLM_MODEL:
                    print(f"[LLM] Found model as: {name}")
                break

        if not model_found:
            if verbose:
                print(f"[LLM] Warning: {LLM_MODEL} not found")
                print(f"[LLM] Available: {model_names}")
                print(f"[LLM] Attempting to pull model...")

            try:
                client.pull(LLM_MODEL)
                print(f"[LLM] Model {LLM_MODEL} pulled successfully")
                return True
            except Exception as e:
                print(f"[LLM] Failed to pull model: {e}")
                return False

        return True

    except Exception as e:
        if verbose:
            print(f"[LLM] Connection failed: {e}")
            print(f"[LLM] Make sure Ollama is running:")
            print(f"[LLM]   ./launch_ollama.sh")
        return False


def initialize_llm(preload: bool = False) -> Tuple[ollama.Client, bool]:
    """
    Initialize LLM with connection testing and optional model preloading

    Returns:
        (client, success): Ollama client and whether initialization succeeded
    """
    client = get_ollama_client()

    # Test connection
    if not test_ollama_connection(client):
        print("[LLM] Ollama not accessible - check SSH tunnel")
        return client, False

    # Preload model if requested
    if preload:
        try:
            print(f"[LLM] Preloading model {LLM_MODEL}...")
            response = client.chat(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": "hello"}],
                options={"timeout": CONNECTION_TIMEOUT}
            )
            print(f"[LLM] Model {LLM_MODEL} loaded and ready")
            return client, True
        except Exception as e:
            print(f"[LLM] Model preload failed: {e}")
            print(f"[LLM] Will load on first request instead")
            return client, True

    return client, True


def chat_with_retry(client, model: str, messages: list, max_retries: int = MAX_RETRIES) -> Optional[dict]:
    """
    Call Ollama chat with retry logic

    Args:
        client: Ollama client
        model: Model name
        messages: Chat messages
        max_retries: Maximum retry attempts

    Returns:
        Response dict or None if all retries failed
    """
    print(f"\n[LLM] chat_with_retry() called")
    print(f"[LLM]   Model: {model}")
    print(f"[LLM]   Message count: {len(messages)}")

    for attempt in range(max_retries):
        try:
            print(f"[LLM] Attempt {attempt + 1}/{max_retries}")

            response = client.chat(
                model=model,
                messages=messages,
                options={"timeout": CONNECTION_TIMEOUT}
            )

            print(f"[LLM] Response received successfully")
            return response

        except Exception as e:
            print(f"[LLM] Attempt {attempt + 1}/{max_retries} failed: {e}")

            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"[LLM] Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"[LLM] All retry attempts exhausted")
                import traceback
                traceback.print_exc()
                return None

    return None


if __name__ == "__main__":
    print("Testing Ollama configuration...")
    client, success = initialize_llm(preload=True)

    if success:
        print("\nConfiguration is valid")
        print(f"  Host: {OLLAMA_HOST}")
        print(f"  Model: {LLM_MODEL}")

        print("\nTesting chat functionality...")
        response = chat_with_retry(
            client,
            LLM_MODEL,
            [{"role": "user", "content": "Say hello in one sentence"}]
        )

        if response:
            print(f"  Response: {response['message']['content']}")
            print("\nChat test successful")
        else:
            print("\nChat test failed")
    else:
        print("\nConfiguration has issues")
        print("  Run: ./launch_ollama.sh")
