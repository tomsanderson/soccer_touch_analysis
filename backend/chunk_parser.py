import json
import os
from typing import Any, Dict, List, Tuple

from openai import OpenAI
from pydantic import ValidationError

from .models import DecomposedEvent, DecomposeResponse, NarrationChunkIn

STRUCTURE_MODEL_ENV = "STRUCTURE_MODEL"

SYSTEM_PROMPT = """You are an analyst that converts natural-language soccer narration into structured events.
Given a narration chunk and its video time window, identify every meaningful soccer event and map it to the schema.

Output strictly valid JSON with this format:
{
  "events": [
    {
      "event_type": "...",
      "team": "...",
      "player_name": "...",
      "player_jersey_number": "...",
      "approximate_time_s": <float seconds within the provided window>,
      "source_phrase": "...",
      "first_touch_quality": "...",
      "on_ball_action_type": "...",
      "action_outcome_detail": "...",
      "post_loss_behaviour": "...",
      ...
    }
  ]
}

Guidelines:
- Narration is conversational; you infer structure.
- Use the provided window [video_start_s, video_end_s] to estimate timestamps. It's acceptable to leave approximate_time_s null if the narration is too vague.
- Retain the relevant snippet of narration for source_phrase.
- Include any schema-aligned fields you can infer (first touch qualities, pass intent, outcomes, reactions). Leave fields absent or null if unknown.
- Order events chronologically.
- If the narration contains no soccer events, return {"events": []}.
"""

EXAMPLE_INPUT = {
    "match_id": "sample-match",
    "period": "1",
    "video_start_s": 30.0,
    "video_end_s": 45.0,
    "transcript_text": "Blue seven brings the ball down calmly, then plays a safe pass back to blue three. Blue three tries a forward ball but it's intercepted. Seven presses right away.",
}

EXAMPLE_OUTPUT = {
    "events": [
        {
            "event_type": "first_touch",
            "team": "Blue",
            "player_jersey_number": "7",
            "approximate_time_s": 32.0,
            "source_phrase": "Blue seven brings the ball down calmly",
            "first_touch_quality": "high",
        },
        {
            "event_type": "on_ball_action",
            "team": "Blue",
            "player_jersey_number": "7",
            "approximate_time_s": 34.0,
            "source_phrase": "plays a safe pass back to blue three",
            "touch_count_before_action": "two_touch",
            "on_ball_action_type": "pass",
            "pass_intent": "safe_recycle",
            "action_outcome_team": "same_team",
            "action_outcome_detail": "completed",
        },
        {
            "event_type": "on_ball_action",
            "team": "Blue",
            "player_jersey_number": "3",
            "approximate_time_s": 37.0,
            "source_phrase": "Blue three tries a forward ball but it's intercepted",
            "on_ball_action_type": "forward_ball",
            "action_outcome_team": "opponent",
            "action_outcome_detail": "intercepted",
        },
        {
            "event_type": "post_loss_reaction",
            "team": "Blue",
            "player_jersey_number": "7",
            "approximate_time_s": 39.0,
            "source_phrase": "Seven presses right away",
            "post_loss_behaviour": "immediate_press",
            "post_loss_outcome": "won_back_possession_team",
            "post_loss_effort_intensity": "high",
        },
    ]
}


def decompose_chunk(
    client: OpenAI, chunk: NarrationChunkIn
) -> Tuple[List[DecomposedEvent], Dict[str, Any]]:
    """
    Send a narration chunk to the LLM and return structured events plus raw JSON.
    """
    structure_model = os.getenv(STRUCTURE_MODEL_ENV)
    if not structure_model:
        raise RuntimeError("STRUCTURE_MODEL environment variable must be set.")

    payload = {
        "chunk": chunk.dict(),
        "example_chunk": EXAMPLE_INPUT,
        "example_output": EXAMPLE_OUTPUT,
    }
    user_prompt = json.dumps(payload, indent=2)

    response = client.responses.create(
        model=structure_model,
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
    )
    raw_text = _extract_response_text(response)
    raw_json = json.loads(raw_text)
    events_data = raw_json.get("events", [])

    events = [DecomposedEvent(**item) for item in events_data]
    return events, raw_json


def _extract_response_text(response: Any) -> str:
    for item in getattr(response, "output", []):
        for content in getattr(item, "content", []):
            if getattr(content, "type", None) in {"output_text", "text"}:
                return content.text
    raise ValueError("LLM response did not contain textual content.")


def validate_response(events: List[DecomposedEvent], raw: Dict[str, Any]) -> DecomposeResponse:
    try:
        return DecomposeResponse(events=events, raw_response=raw)
    except ValidationError as exc:
        raise exc
