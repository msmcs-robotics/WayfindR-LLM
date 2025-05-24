# LLM configuration (shared between all components)
LLM_MODEL = "llama3.3:70b-instruct-q5_K_M"  # Specify the model once
import ollama

def get_ollama_client():
    """
    Returns an Ollama client with consistent configuration
    """
    return ollama

def get_model_name():
    """
    Returns the configured model name
    """
    return LLM_MODEL