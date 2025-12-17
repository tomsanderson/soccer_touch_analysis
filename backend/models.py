from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, validator


class LLMEventPrediction(BaseModel):
    """Structured event returned by the LLM parser."""

    segment_index: int = Field(..., ge=0)
    event_type: Literal["first_touch", "on_ball_action", "post_loss_reaction"]
    team: str
    player_jersey_number: str
    source_phrase: Optional[str] = None

    # First-touch specific
    first_touch_quality: Optional[Literal["high", "medium", "low"]] = None
    first_touch_result: Optional[
        Literal["controlled", "rebound_free_space", "rebound_opponent"]
    ] = None

    # On-ball action specific
    touch_count_before_action: Optional[
        Literal["one_touch", "two_touch", "three_plus"]
    ] = None
    on_ball_action_type: Optional[
        Literal["pass", "forward_ball", "service", "clearance", "shot", "carry", "carry_pass"]
    ] = None
    carry_flag: Optional[bool] = None
    pass_intent: Optional[
        Literal[
            "safe_recycle",
            "line_breaking",
            "switch_of_play",
            "through_ball",
            "service_into_box",
            "other",
        ]
    ] = None
    action_outcome_team: Optional[
        Literal["same_team", "opponent", "out_of_play", "loose"]
    ] = None
    action_outcome_detail: Optional[str] = None
    next_possession_team: Optional[
        Literal["same_team", "opponent", "contested"]
    ] = None

    # Post-loss reaction specific
    post_loss_behaviour: Optional[
        Literal["immediate_press", "track_runner", "token_pressure", "no_reaction"]
    ] = None
    post_loss_outcome: Optional[
        Literal[
            "won_back_possession_self",
            "won_back_possession_team",
            "forced_error_only",
            "no_effect",
            "negative_effect",
        ]
    ] = None
    post_loss_effort_intensity: Optional[
        Literal["high", "medium", "low"]
    ] = None

    def ensure_required_fields(self) -> None:
        if self.event_type == "first_touch":
            missing = [
                name
                for name in ("first_touch_quality", "first_touch_result")
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"Missing fields for first_touch: {missing}")
        elif self.event_type == "on_ball_action":
            missing = [
                name
                for name in (
                    "touch_count_before_action",
                    "on_ball_action_type",
                    "action_outcome_team",
                    "action_outcome_detail",
                    "next_possession_team",
                )
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"Missing fields for on_ball_action: {missing}")
        elif self.event_type == "post_loss_reaction":
            missing = [
                name
                for name in (
                    "post_loss_behaviour",
                    "post_loss_outcome",
                    "post_loss_effort_intensity",
                )
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"Missing fields for post_loss_reaction: {missing}")

    @validator("team", "player_jersey_number", pre=True)
    def _strip_whitespace(cls, value: Optional[str]) -> Optional[str]:
        if isinstance(value, str):
            return value.strip()
        return value


class NarrationChunkIn(BaseModel):
    match_id: str
    period: Optional[int] = None
    video_start_s: float = Field(..., ge=0)
    video_end_s: float = Field(..., gt=0)
    transcript_text: str
    team_context: Optional[str] = None

    @validator("video_end_s")
    def _end_after_start(cls, value: float, values: Dict[str, Any]) -> float:
        start = values.get("video_start_s")
        if start is not None and value <= start:
            raise ValueError("video_end_s must be greater than video_start_s")
        return value


class DecomposedEvent(BaseModel):
    event_type: Optional[str] = None
    team: Optional[str] = None
    player_name: Optional[str] = None
    player_jersey_number: Optional[str] = None
    approximate_time_s: Optional[float] = None
    source_phrase: Optional[str] = None
    inference_confidence: Optional[Literal["low", "medium", "high"]] = None

    # Optional schema-aligned fields
    first_touch_quality: Optional[str] = None
    first_touch_result: Optional[str] = None
    on_ball_action_type: Optional[str] = None
    touch_count_before_action: Optional[str] = None
    pass_intent: Optional[str] = None
    action_outcome_team: Optional[str] = None
    action_outcome_detail: Optional[str] = None
    post_loss_behaviour: Optional[str] = None
    post_loss_outcome: Optional[str] = None
    post_loss_effort_intensity: Optional[str] = None
    extra_fields: Optional[Dict[str, Any]] = None


class DecomposeResponse(BaseModel):
    events: List[DecomposedEvent]
    raw_response: Optional[Dict[str, Any]] = None
    chunk_id: Optional[int] = None
    decomposition_id: Optional[int] = None


class StatsBombRawIn(BaseModel):
    source: str
    file_type: str
    external_id: Optional[str] = None
    schema_version: Optional[str] = None
    payload: Dict[str, Any]


class StatsBombMatchProjectionIn(BaseModel):
    match: Dict[str, Any]
    events: List[Dict[str, Any]] = []
    source: Optional[str] = None
    schema_version: Optional[str] = None
