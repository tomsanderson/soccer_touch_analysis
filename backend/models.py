from typing import Literal, Optional

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
