import subprocess
import requests
import time
import shutil
import logging
from typing import Tuple
from .config import settings

logger = logging.getLogger(__name__)

def check_ollama_available(url: str = None) -> bool:
    """Check if Ollama service is responsive."""
    target_url = url or settings.OLLAMA_URL
    try:
        res = requests.get(f"{target_url}/api/tags", timeout=2)
        return res.status_code == 200
    except requests.RequestException:
        return False

def ensure_ollama_running(model_name: str = None) -> Tuple[bool, str]:
    """
    Ensure Ollama is running on Windows local environment.
    Returns (is_available, message).
    """
    target_url = settings.OLLAMA_URL
    target_model = model_name or settings.OLLAMA_MODEL

    if check_ollama_available(target_url):
        logger.info(f"Ollama local is active at {target_url}")
    else:
        logger.info("Ollama is not running. Attempting to start local Ollama service...")
        ollama_bin = shutil.which("ollama")
        if not ollama_bin:
            msg = (
                "Ollama executable not found in PATH. "
                "Rule-based extraction will be used as primary engine. "
                "To enable vision LLM for complex tables, install Ollama from https://ollama.com/download/OllamaSetup.exe"
            )
            logger.warning(msg)
            return False, msg

        try:
            subprocess.Popen([ollama_bin, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
        except Exception as e:
            msg = f"Failed to start Ollama automatically: {e}"
            logger.warning(msg)
            return False, msg

    if not check_ollama_available(target_url):
        return False, "Ollama service unavailable."

    # Check model tags
    try:
        res = requests.get(f"{target_url}/api/tags", timeout=5).json()
        models = [m.get("name", "") for m in res.get("models", [])]
        if not any(target_model in m for m in models):
            logger.info(f"Model '{target_model}' not found locally. Pulling model via Ollama...")
            subprocess.run(["ollama", "pull", target_model], check=True)
            logger.info(f"Model '{target_model}' successfully pulled.")
        return True, f"Ollama model '{target_model}' is ready."
    except Exception as e:
        logger.warning(f"Error checking or pulling Ollama model: {e}")
        return True, f"Ollama is active, but model status warning: {e}"
