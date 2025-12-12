import json
import logging
import os
from typing import Any, Dict, List, Tuple

from openai import OpenAI, OpenAIError

from . import parser as rule_parser
from .models import LLMEventPrediction

STRUCTURE_MODEL_ENV = "STRUCTURE_MODEL"

SYSTEM_PROMPT = """You are an assistant that converts soccer narration transcripts into structured event data.
You must output valid JSON with this shape:
{
  "events": [
    {
      "segment_index": NUMBER,
      "event_type": "first_touch" | "on_ball_action" | "post_loss_reaction",
      "team": "Blue" | "White",
      "player_jersey_number": "string",
      "source_phrase": "original phrase",
      // Additional fields depending on event_type (see below)
    }
  ]
}

Rules:
1. Use the transcript segments provided by the user. Each segment has an index and start time.
2. A single segment may describe multiple events; include multiple entries referencing the same segment_index if needed.
3. Only emit events for clear narrations that match the Version 1 grammar.
4. Populate fields:
   - first_touch: require first_touch_quality (high|medium|low) and first_touch_result (controlled|rebound_free_space|rebound_opponent).
   - on_ball_action: require touch_count_before_action (one_touch|two_touch|three_plus),
                     on_ball_action_type (pass|forward_ball|service|clearance|shot),
                     action_outcome_team (same_team|opponent|out_of_play|loose),
                     action_outcome_detail (string),
                     next_possession_team (same_team|opponent|contested).
                     Optional: carry_flag, pass_intent (safe_recycle|line_breaking|switch_of_play|through_ball|service_into_box|other).
   - post_loss_reaction: require post_loss_behaviour (immediate_press|track_runner|token_pressure|no_reaction),
                         post_loss_outcome (won_back_possession_self|won_back_possession_team|forced_error_only|no_effect|negative_effect),
                         post_loss_effort_intensity (high|medium|low).
5. Always include the exact short phrase you interpreted in "source_phrase".
6. If a segment is unrelated (e.g., "Mark ten minutes"), omit it.
7. Return strictly valid JSON and nothing else.
"""

FEW_SHOT_SEGMENTS = [
    {"index": 0, "start": 0.0, "text": "Blue seven first touch high, controlled."},
    {
        "index": 1,
        "start": 3.2,
        "text": "Blue seven two-touch pass, safe recycle to center back, completed.",
    },
    {"index": 2, "start": 6.4, "text": "After losing it, Blue seven immediate press, wins it back herself."},
]

FEW_SHOT_OUTPUT = {
    "events": [
        {
            "segment_index": 0,
            "event_type": "first_touch",
            "team": "Blue",
            "player_jersey_number": "7",
            "source_phrase": "Blue seven first touch high, controlled.",
            "first_touch_quality": "high",
            "first_touch_result": "controlled",
        },
        {
            "segment_index": 1,
            "event_type": "on_ball_action",
            "team": "Blue",
            "player_jersey_number": "7",
            "source_phrase": "Blue seven two-touch pass, safe recycle to center back, completed.",
            "touch_count_before_action": "two_touch",
            "on_ball_action_type": "pass",
            "pass_intent": "safe_recycle",
            "action_outcome_team": "same_team",
            "action_outcome_detail": "completed",
            "next_possession_team": "same_team",
        },
        {
            "segment_index": 2,
            "event_type": "post_loss_reaction",
            "team": "Blue",
            "player_jersey_number": "7",
            "source_phrase": "After losing it, Blue seven immediate press, wins it back herself.",
            "post_loss_behaviour": "immediate_press",
            "post_loss_outcome": "won_back_possession_self",
            "post_loss_effort_intensity": "high",
        },
    ]
}


class LLMParsingError(RuntimeError):
    pass


def parse_transcript_segments(
    segments: List[Dict[str, Any]],
    *,
    match_id: str,
    period: str,
    offset_seconds: float = 0.0,
    client: OpenAI,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Attempt to parse narration with the LLM. If unavailable or the response is invalid, fall back to the rule parser.
    """
    structure_model = os.getenv(STRUCTURE_MODEL_ENV)
    api_key = os.getenv("OPENAI_API_KEY")
    if not client or not api_key or not structure_model:
        logging.info("LLM parser disabled or misconfigured; using rule parser.")
        events = rule_parser.parse_transcript_segments(
            segments,
            match_id=match_id,
            period=period,
            offset_seconds=offset_seconds,
        )
        return events, "rule"

    try:
        predictions = _request_predictions(
            client=client,
            structure_model=structure_model,
            segments=segments,
        )
        if not predictions:
            raise LLMParsingError("No events returned by LLM.")
        events = _build_events_from_predictions(
            predictions=predictions,
            segments=segments,
            match_id=match_id,
            period=period,
            offset_seconds=offset_seconds,
        )
        logging.info("LLM parser successfully produced %s events.", len(events))
        return events, "llm"
    except (OpenAIError, LLMParsingError, ValueError, json.JSONDecodeError) as exc:
        logging.warning("LLM parser failed, falling back to rule parser: %s", exc)
        events = rule_parser.parse_transcript_segments(
            segments,
            match_id=match_id,
            period=period,
            offset_seconds=offset_seconds,
        )
        return events, "rule"


def _request_predictions(
    *,
    client: OpenAI,
    structure_model: str,
    segments: List[Dict[str, Any]],
) -> List[LLMEventPrediction]:
    formatted_segments = [
        {"index": idx, "start": float(seg.get("start", 0.0)), "text": str(seg.get("text", ""))}
        for idx, seg in enumerate(segments)
    ]
    payload = {
        "instructions": "Transform the following transcript segments into structured events.",
        "segments": formatted_segments,
        "example_segments": FEW_SHOT_SEGMENTS,
        "example_output": FEW_SHOT_OUTPUT,
    }
    user_prompt = json.dumps(payload, indent=2)

    response = client.responses.create(
        model=structure_model,
        input=[
            {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
        ],
    )
    content = _extract_response_text(response)
    data = json.loads(content)
    events_data = data.get("events", [])

    predictions: List[LLMEventPrediction] = []
    for item in events_data:
        prediction = LLMEventPrediction(**item)
        prediction.ensure_required_fields()
        predictions.append(prediction)
    return predictions


def _extract_response_text(response: Any) -> str:
    for item in getattr(response, "output", []):
        for content in getattr(item, "content", []):
            if getattr(content, "type", None) == "output_text":
                return content.text
            if getattr(content, "type", None) == "text":
                return content.text
    raise LLMParsingError("No textual content in LLM response.")


def _build_events_from_predictions(
    *,
    predictions: List[LLMEventPrediction],
    segments: List[Dict[str, Any]],
    match_id: str,
    period: str,
    offset_seconds: float,
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for counter, prediction in enumerate(predictions, start=1):
        segment = _safe_segment_lookup(segments, prediction.segment_index)
        video_time = float(segment.get("start", 0.0)) + offset_seconds
        source_phrase = prediction.source_phrase or str(segment.get("text", "")).strip()
        event = {
            "event_id": f"{match_id}-{counter}",
            "match_id": match_id,
            "period": period,
            "video_time_s": video_time,
            "team": prediction.team,
            "player_id": None,
            "player_name": None,
            "player_jersey_number": prediction.player_jersey_number,
            "player_role": None,
            "event_type": prediction.event_type,
            "possession_id": None,
            "sequence_id": None,
            "source_phrase": source_phrase,
            "zone_start": None,
            "zone_end": None,
            "tags": None,
            "comment": None,
            "first_touch_quality": prediction.first_touch_quality,
            "first_touch_result": prediction.first_touch_result,
            "possession_after_touch": None,
            "maintained_possession_bool": None,
            "on_ball_action_type": prediction.on_ball_action_type,
            "touch_count_before_action": prediction.touch_count_before_action,
            "carry_flag": prediction.carry_flag,
            "pass_intent": prediction.pass_intent,
            "action_outcome_team": prediction.action_outcome_team,
            "action_outcome_detail": prediction.action_outcome_detail,
            "next_possession_team": prediction.next_possession_team,
            "trigger_event_id": None,
            "post_loss_behaviour": prediction.post_loss_behaviour,
            "post_loss_effort_intensity": prediction.post_loss_effort_intensity,
            "post_loss_outcome": prediction.post_loss_outcome,
            "post_loss_disruption_rating": None,
        }
        events.append(event)
    return events


def _safe_segment_lookup(segments: List[Dict[str, Any]], index: int) -> Dict[str, Any]:
    if 0 <= index < len(segments):
        return segments[index]
    return {"start": 0.0, "text": ""}
