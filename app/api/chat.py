import base64
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import Optional
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel
from groq import Groq
from cerebras.cloud.sdk import Cerebras
from app.db.database import get_db
from app.db import models
from app.core.cost_engine import estimate_tokens, j_space_optimize
from app.core.model_router import select_model, calculate_cost_for_model, MODELS
from app.core.config import GROQ_API_KEY, CEREBRAS_API_KEY

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])

groq_client = Groq(api_key=GROQ_API_KEY)
cerebras_client = Cerebras(api_key=CEREBRAS_API_KEY)

# Updated to current (non-deprecated) Groq models
GROQ_MODEL_MAP = {
    "heavy": "openai/gpt-oss-120b",
    "light": "openai/gpt-oss-20b",
}

CEREBRAS_MODEL_MAP = {
    "heavy": "gpt-oss-120b",
    "light": "llama3.1-8b",
}

VISION_MODEL = "qwen/qwen3.6-27b"  # Groq's current vision-capable model

PROVIDER_FALLBACK_ORDER = ["cerebras", "grok"]


class ChatRequest(BaseModel):
    session_id: int
    prompt: str
    expected_output_tokens: int = 500
    preferred_provider: str = "grok"


def call_provider(provider_name: str, model_tier: str, prompt: str):
    if provider_name == "cerebras":
        model_name = CEREBRAS_MODEL_MAP[model_tier]
        completion = cerebras_client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
        )
    else:
        model_name = GROQ_MODEL_MAP[model_tier]
        completion = groq_client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
        )

    return {
        "model_name": model_name,
        "ai_text": completion.choices[0].message.content,
        "input_tokens": completion.usage.prompt_tokens,
        "output_tokens": completion.usage.completion_tokens,
    }


def call_vision(prompt: str, image_b64: str, mime_type: str):
    """Send an image + prompt to Groq's vision model."""
    completion = groq_client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt or "Describe this image."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                    },
                ],
            }
        ],
    )
    return {
        "model_name": VISION_MODEL,
        "ai_text": completion.choices[0].message.content,
        "input_tokens": completion.usage.prompt_tokens,
        "output_tokens": completion.usage.completion_tokens,
    }


def run_chat_logic(db: DBSession, session_id: int, prompt: str, preferred_provider: str,
                    image_bytes: Optional[bytes] = None, image_mime: Optional[str] = None):
    session = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    usage_percent = (session.used / session.budget * 100) if session.budget > 0 else 100
    if usage_percent >= 100:
        raise HTTPException(status_code=402, detail="Budget exhausted")

    selected_model = select_model(preferred_provider, usage_percent)
    alt_tier = "light" if selected_model["tier"] == "heavy" else "heavy"
    alt_model = MODELS.get(preferred_provider, MODELS["grok"])[alt_tier]

    optimized_prompt = j_space_optimize(prompt, groq_client)
    optimized_input_tokens = estimate_tokens(optimized_prompt)

    result = None
    used_provider = None
    fallback_happened = False
    last_error = None

    if image_bytes is not None:
        # Image requests always go through the vision model (no fallback chain for images yet)
        try:
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            result = call_vision(prompt, image_b64, image_mime or "image/png")
            used_provider = "grok"
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Vision API error: {str(e)}")
    else:
        providers_to_try = [preferred_provider] + [
            p for p in PROVIDER_FALLBACK_ORDER if p != preferred_provider
        ]
        for i, provider_name in enumerate(providers_to_try):
            try:
                result = call_provider(provider_name, selected_model["tier"], prompt)
                used_provider = provider_name
                fallback_happened = (i > 0)
                break
            except Exception as e:
                last_error = str(e)
                continue

        if result is None:
            raise HTTPException(status_code=502, detail=f"All providers failed. Last error: {last_error}")

    real_input_tokens = result["input_tokens"]
    real_output_tokens = result["output_tokens"]
    ai_text = result["ai_text"]
    model_name = result["model_name"]

    selected_cost = calculate_cost_for_model(real_input_tokens, real_output_tokens, selected_model)
    alt_cost = calculate_cost_for_model(optimized_input_tokens, real_output_tokens, alt_model)

    token_reduction_pct = round((1 - optimized_input_tokens / real_input_tokens) * 100, 2) if real_input_tokens > 0 else 0
    cost_reduction_pct = round((1 - alt_cost / selected_cost) * 100, 2) if selected_cost > 0 else 0

    decision = "SUCCESS"
    if fallback_happened:
        decision = "FALLBACK_PROVIDER_SWITCH"
    elif selected_model["tier"] == "light":
        decision = "WARNING_SWITCHED_TO_LIGHT"

    session.used += selected_cost
    db.add(models.RequestLog(
        session_id=session.id,
        input_tokens=real_input_tokens,
        output_tokens=real_output_tokens,
        normal_cost=selected_cost,
        optimized_cost=alt_cost,
        model_used=model_name,
    ))
    db.commit()

    return {
        "decision": decision,
        "provider": used_provider,
        "requested_provider": preferred_provider,
        "fallback_happened": fallback_happened,
        "model_used": model_name,
        "tier": selected_model["tier"],
        "cost_charged": selected_cost,
        "input_tokens": real_input_tokens,
        "output_tokens": real_output_tokens,
        "total_tokens": real_input_tokens + real_output_tokens,
        "session_remaining_budget": round(session.budget - session.used, 6),
        "usage_percent": round(usage_percent, 2),
        "ai_response": ai_text,
        "alternate_route": {
            "model_used": (CEREBRAS_MODEL_MAP if used_provider == "cerebras" else GROQ_MODEL_MAP)[alt_tier],
            "tier": alt_tier,
            "cost": alt_cost,
            "input_tokens": optimized_input_tokens,
            "output_tokens": real_output_tokens,
            "token_reduction_percent": token_reduction_pct,
            "cost_reduction_percent": cost_reduction_pct,
        }
    }


@router.post("/chat")
def chat(req: ChatRequest, db: DBSession = Depends(get_db)):
    return run_chat_logic(db, req.session_id, req.prompt, req.preferred_provider)


@router.post("/chat-with-file")
async def chat_with_file(
    session_id: int = Form(...),
    prompt: str = Form(""),
    preferred_provider: str = Form("grok"),
    file: UploadFile = File(...),
    db: DBSession = Depends(get_db),
):
    contents = await file.read()
    is_image = (file.content_type or "").startswith("image/")

    if is_image:
        return run_chat_logic(
            db, session_id, prompt, preferred_provider,
            image_bytes=contents, image_mime=file.content_type
        )
    else:
        try:
            text_content = contents.decode("utf-8", errors="ignore")
        except Exception:
            raise HTTPException(status_code=400, detail="Could not read file as text")
        combined_prompt = f"{prompt}\n\n[Attached file: {file.filename}]\n{text_content}"
        return run_chat_logic(db, session_id, combined_prompt, preferred_provider)