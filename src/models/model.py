import os
import time
import threading
from dotenv import load_dotenv , find_dotenv
from langchain_mistralai import ChatMistralAI

# Load environment variables
load_dotenv(find_dotenv())

# ── LLM instance cache (reuse across calls to avoid re-init overhead) ──
_llm_cache: dict = {}
_llm_lock = threading.Lock()

# ── Simple rate limiter: minimum seconds between Mistral API calls ──
_last_call_time = 0.0
_rate_lock = threading.Lock()
MIN_CALL_INTERVAL = 1.0  # seconds between LLM calls (adjust if still hitting limits)

def _rate_limit_wait():
    """Enforce a minimum interval between Mistral API calls."""
    global _last_call_time
    with _rate_lock:
        now = time.time()
        elapsed = now - _last_call_time
        if elapsed < MIN_CALL_INTERVAL:
            wait = MIN_CALL_INTERVAL - elapsed
            print(f"   ⏳ Rate limit: waiting {wait:.1f}s")
            time.sleep(wait)
        _last_call_time = time.time()

def get_llm(model_type="medium", temperature=None):
    """
    Returns a cached Mistral LLM instance.
    Reuses the same instance for the same model_type to avoid overhead.
    
    Temperature defaults:
      - small/medium: 0.1 (deterministic — classification, tool calling)
      - large: 0.3
    """
    global _llm_cache
    
    # Build cache key from both model_type and temperature
    default_temp = 0.3 if model_type == "large" else 0.1
    temp = temperature if temperature is not None else default_temp
    cache_key = f"{model_type}_{temp}"
    
    with _llm_lock:
        if cache_key in _llm_cache:
            return _llm_cache[cache_key]
    
    # Map model types to Mistral model names
    if model_type == "small":
        model_name = "mistral-small-latest" 
    elif model_type == "medium":
        model_name = "mistral-medium-latest"
    elif model_type == "large":
        model_name = "mistral-large-latest"    
    else:
        model_name = "mistral-medium-latest"

    print(f"Loading LLM: {model_name} (temp={temp}, cached as {cache_key})")

    llm = ChatMistralAI(
        model=model_name,
        temperature=temp,
        mistral_api_key=os.getenv("MISTRAL_API_KEY"),
        max_retries=3,
        timeout=90
    )

    with _llm_lock:
        _llm_cache[cache_key] = llm
    
    return llm