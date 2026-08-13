import re
import tiktoken

INPUT_RATE = 0.01
OUTPUT_RATE = 0.03

_encoder = tiktoken.get_encoding("cl100k_base")


def estimate_tokens(text: str) -> int:
    return len(_encoder.encode(text))


def calculate_cost(input_tokens: int, output_tokens: int) -> float:
    cost = (input_tokens / 1000) * INPUT_RATE + (output_tokens / 1000) * OUTPUT_RATE
    return round(cost, 6)


def j_space_optimize(text: str, client) -> str:
    """
    J-Space: real LLM-based compression.
    Uses a cheap/fast model to rewrite the prompt with the same
    meaning but fewer tokens.
    """
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": "Rewrite the user's message to preserve its exact meaning and intent, using the fewest possible words. Return ONLY the rewritten text, nothing else."
                },
                {"role": "user", "content": text}
            ],
            temperature=0,
            max_tokens=200,
        )
        compressed = response.choices[0].message.content.strip()
        return compressed if compressed else text
    except Exception:
        return text  # fallback: if compression fails, use original


def j_lens_measure(original_tokens: int, optimized_tokens: int, original_cost: float, optimized_cost: float) -> dict:
    """J-Lens: measure actual savings from J-Space optimization."""
    token_reduction_pct = 0.0
    cost_reduction_pct = 0.0
    if original_tokens > 0:
        token_reduction_pct = round((1 - optimized_tokens / original_tokens) * 100, 2)
    if original_cost > 0:
        cost_reduction_pct = round((1 - optimized_cost / original_cost) * 100, 2)
    return {
        "token_reduction_percent": token_reduction_pct,
        "cost_reduction_percent": cost_reduction_pct,
    }