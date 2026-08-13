import os
import httpx
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
XAI_API_KEY = os.getenv("XAI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Map our internal tier names -> real API model names
REAL_MODEL_MAP = {
    "grok-heavy": "llama-3.3-70b-versatile",
    "grok-light": "llama-3.1-8b-instant",
    "gpt-heavy": "gpt-4o",
    "gpt-light": "gpt-4o-mini",
    "gemini-heavy": "gemini-1.5-pro",
    "gemini-light": "gemini-1.5-flash",
}


def call_grok(prompt: str, model_name: str, max_tokens: int) -> dict:
    real_model = REAL_MODEL_MAP.get(model_name, model_name)
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": real_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return {
        "text": data["choices"][0]["message"]["content"],
        "input_tokens": data["usage"]["prompt_tokens"],
        "output_tokens": data["usage"]["completion_tokens"],
    }


def call_gpt(prompt: str, model_name: str, max_tokens: int) -> dict:
    real_model = REAL_MODEL_MAP.get(model_name, model_name)
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": real_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return {
        "text": data["choices"][0]["message"]["content"],
        "input_tokens": data["usage"]["prompt_tokens"],
        "output_tokens": data["usage"]["completion_tokens"],
    }


def call_gemini(prompt: str, model_name: str, max_tokens: int) -> dict:
    real_model = REAL_MODEL_MAP.get(model_name, model_name)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{real_model}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    usage = data.get("usageMetadata", {})
    return {
        "text": data["candidates"][0]["content"]["parts"][0]["text"],
        "input_tokens": usage.get("promptTokenCount", 0),
        "output_tokens": usage.get("candidatesTokenCount", 0),
    }


def call_llm(provider: str, model_name: str, prompt: str, max_tokens: int) -> dict:
    if provider == "grok":
        return call_grok(prompt, model_name, max_tokens)
    elif provider == "gpt":
        return call_gpt(prompt, model_name, max_tokens)
    elif provider == "gemini":
        return call_gemini(prompt, model_name, max_tokens)
    else:
        raise ValueError(f"Unknown provider: {provider}")