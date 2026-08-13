MODELS = {
    "grok": {
        "heavy": {"name": "grok-heavy", "input_rate": 0.015, "output_rate": 0.045},
        "light": {"name": "grok-light", "input_rate": 0.005, "output_rate": 0.015},
    },
    "gpt": {
        "heavy": {"name": "gpt-heavy", "input_rate": 0.020, "output_rate": 0.060},
        "light": {"name": "gpt-light", "input_rate": 0.006, "output_rate": 0.018},
    },
    "cerebras": {
        "heavy": {"name": "gpt-oss-120b", "input_rate": 0.012, "output_rate": 0.036},
        "light": {"name": "llama3.1-8b", "input_rate": 0.004, "output_rate": 0.012},
    },
}

def select_model(preferred_provider: str, usage_percent: float):
    provider = MODELS.get(preferred_provider, MODELS["grok"])
    tier = "light" if usage_percent >= 80 else "heavy"
    model = provider[tier]
    return {
        "provider": preferred_provider,
        "tier": tier,
        "model_name": model["name"],
        "input_rate": model["input_rate"],
        "output_rate": model["output_rate"],
    }

def calculate_cost_for_model(input_tokens: int, output_tokens: int, model: dict) -> float:
    cost = (input_tokens / 1000) * model["input_rate"] + (output_tokens / 1000) * model["output_rate"]
    return round(cost, 6)