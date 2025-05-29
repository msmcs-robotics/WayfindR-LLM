# utils.py
from datetime import datetime
from typing import Dict, Any
from uuid import uuid4

def generate_conversation_id(prefix: str, identifier: str) -> str:
    return f"{prefix}_{identifier}_{str(uuid4())[:8]}"

def success_response(data: Dict) -> Dict[str, Any]:
    return {"success": True, "data": data}

def error_response(error: str) -> Dict[str, Any]:
    return {"success": False, "error": error}