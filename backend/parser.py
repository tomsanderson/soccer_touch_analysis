import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

FIRST_TOUCH_RE = re.compile(
    r"^(?P<team>Blue|White)\s+"
    r"(?P<player>[A-Za-z0-9]+)\s+"
    r"first touch\s+"
    r"(?P<quality>high|medium|low)\s*,?\s*"
    r"(?P<result>controlled|rebound free space|rebound to opponent)\.?$",
    re.IGNORECASE,
)

ON_BALL_RE = re.compile(
    r"^(?P<team>Blue|White)\s+"
    r"(?P<player>[A-Za-z0-9]+)\s+"
    r"(?P<touch_count>one|two|three-plus)-touch\s+"
    r"(?P<action>pass|forward ball|service|clearance|shot)"
    r"\s*,?\s*(?P<tail>.+)$",
    re.IGNORECASE,
)

POST_LOSS_RE = re.compile(
    r"^after losing it,?\s*"
    r"(?P<team>Blue|White)\s+"
    r"(?P<player>[A-Za-z0-9]+)\s+"
    r"(?P<behaviour>immediate press|track runner|token pressure|stops and watches|gives up)\s*,?\s*"
    r"(?P<outcome_clause>.+)$",
    re.IGNORECASE,
)

COMPLETED_RE = re.compile(r"^completed(?:\s+to\s+(?P<target>.+))?\.?$", re.IGNORECASE)
TO_OPPONENT_RE = re.compile(
    r"^(?:to\s+opponent|intercepted(?:\s+by\s+opponent)?)\.?$", re.IGNORECASE
)
OUT_FOR_RE = re.compile(r"^out\s+for\s+(?P<restart>throw|goal kick|corner)\.?$", re.IGNORECASE)
BLOCKED_RE = re.compile(r"^blocked\.?$", re.IGNORECASE)

SPOKEN_NUMBER_MAP = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
}

MARKER_PREFIXES = (
    "first half",
    "second half",
    "mark",
)


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class ParserState:
    match_id: str
    period: str
    offset_seconds: float = 0.0
    event_counter: int = 0
    last_loss_event_id: Optional[str] = None
    current_possession_id: int = 0
    possession_owner_team: Optional[str] = None
    possession_open: bool = False

    def next_event_id(self) -> str:
        self.event_counter += 1
        return f"{self.match_id}-{self.event_counter}"

    def start_or_continue_possession(self, team: str) -> str:
        if not self.possession_open or self.possession_owner_team != team:
            self.current_possession_id += 1
            self.possession_owner_team = team
        self.possession_open = True
        return str(self.current_possession_id)

    def end_possession(self) -> None:
        self.possession_open = False
        self.possession_owner_team = None


def parse_transcript_segments(
    segments: Sequence[Dict[str, Any]],
    *,
    match_id: str,
    period: str,
    offset_seconds: float = 0.0,
) -> List[Dict[str, Any]]:
    """Parse transcript segments into structured events using the V1 grammar."""
    state = ParserState(match_id=match_id, period=period, offset_seconds=offset_seconds)
    events: List[Dict[str, Any]] = []

    for raw_segment in segments:
        segment = _to_segment(raw_segment)
        for raw_text in _split_segment_text(segment.text):
            if not raw_text:
                continue
            normalized = _normalize_phrase(raw_text)
            if not normalized:
                continue
            if any(normalized.startswith(prefix) for prefix in MARKER_PREFIXES):
                continue

            event: Optional[Dict[str, Any]] = None
            event = _parse_first_touch(state, segment, raw_text, normalized)
            if event is None:
                event = _parse_on_ball_action(state, segment, raw_text, normalized)
            if event is None:
                event = _parse_post_loss_reaction(state, segment, raw_text, normalized)

            if event:
                events.append(event)

    return events


def _to_segment(data: Dict[str, Any]) -> Segment:
    return Segment(
        start=float(data.get("start", 0.0)),
        end=float(data.get("end", 0.0)),
        text=str(data.get("text", "")),
    )


def _parse_first_touch(
    state: ParserState,
    segment: Segment,
    raw_text: str,
    normalized_text: str,
) -> Optional[Dict[str, Any]]:
    match = FIRST_TOUCH_RE.match(normalized_text)
    if not match:
        return None

    team = match.group("team").capitalize()
    player_token = match.group("player")
    player_number = _normalize_player(player_token)
    quality = match.group("quality").lower()
    result_raw = match.group("result").lower()

    if result_raw == "controlled":
        first_touch_result = "controlled"
        possession_after = "same_player"
    elif result_raw == "rebound free space":
        first_touch_result = "rebound_free_space"
        possession_after = "loose"
    else:
        first_touch_result = "rebound_opponent"
        possession_after = "opponent"

    maintained_possession = possession_after in {"same_player", "same_team_other_player"}

    event = _build_base_event(
        state,
        segment,
        team=team,
        player_number=player_number,
        event_type="first_touch",
        source_phrase=raw_text,
    )
    possession_id = state.start_or_continue_possession(team)
    event["possession_id"] = possession_id
    event["sequence_id"] = possession_id

    event.update(
        {
            "first_touch_quality": quality,
            "first_touch_result": first_touch_result,
            "possession_after_touch": possession_after,
            "maintained_possession_bool": maintained_possession,
        }
    )

    if not maintained_possession:
        if possession_after == "opponent":
            state.last_loss_event_id = event["event_id"]
        state.end_possession()

    return event


def _parse_on_ball_action(
    state: ParserState,
    segment: Segment,
    raw_text: str,
    normalized_text: str,
) -> Optional[Dict[str, Any]]:
    match = ON_BALL_RE.match(normalized_text)
    if not match:
        return None

    team = match.group("team").capitalize()
    player_number = _normalize_player(match.group("player"))
    touch_count = _map_touch_count(match.group("touch_count").lower())
    action_type = _map_action_type(match.group("action").lower())
    tail = match.group("tail").strip()
    pass_intent, outcome_clause = _extract_intent_and_outcome(tail)
    if action_type not in {"pass", "forward_ball", "service"}:
        pass_intent = None
    outcome = _parse_on_ball_outcome(outcome_clause, action_type)

    event = _build_base_event(
        state,
        segment,
        team=team,
        player_number=player_number,
        event_type="on_ball_action",
        source_phrase=raw_text,
    )

    if state.possession_open and state.possession_owner_team == team:
        event["possession_id"] = str(state.current_possession_id)
        event["sequence_id"] = str(state.current_possession_id)

    event.update(
        {
            "touch_count_before_action": touch_count,
            "on_ball_action_type": action_type,
            "carry_flag": False,
            "pass_intent": pass_intent,
            "action_outcome_team": outcome["action_outcome_team"],
            "action_outcome_detail": outcome["action_outcome_detail"],
            "next_possession_team": outcome["next_possession_team"],
        }
    )

    if outcome["action_outcome_team"] in {"opponent", "out_of_play"}:
        state.last_loss_event_id = event["event_id"]
        state.end_possession()
    elif outcome["action_outcome_team"] == "loose":
        state.end_possession()

    return event


def _parse_post_loss_reaction(
    state: ParserState,
    segment: Segment,
    raw_text: str,
    normalized_text: str,
) -> Optional[Dict[str, Any]]:
    match = POST_LOSS_RE.match(normalized_text)
    if not match:
        return None

    team = match.group("team").capitalize()
    player_number = _normalize_player(match.group("player"))
    behaviour = _map_post_loss_behaviour(match.group("behaviour").lower())
    outcome_text = match.group("outcome_clause").strip().lower()
    outcome = _map_post_loss_outcome(outcome_text)

    if behaviour in {"immediate_press", "track_runner"}:
        intensity = "high"
    elif behaviour == "token_pressure":
        intensity = "medium"
    else:
        intensity = "low"

    event = _build_base_event(
        state,
        segment,
        team=team,
        player_number=player_number,
        event_type="post_loss_reaction",
        source_phrase=raw_text,
    )
    event.update(
        {
            "trigger_event_id": state.last_loss_event_id,
            "post_loss_behaviour": behaviour,
            "post_loss_outcome": outcome,
            "post_loss_effort_intensity": intensity,
        }
    )

    return event


def _map_touch_count(value: str) -> str:
    if value == "one":
        return "one_touch"
    if value == "two":
        return "two_touch"
    return "three_plus"


def _map_action_type(value: str) -> str:
    if value == "pass":
        return "pass"
    if value == "forward ball":
        return "forward_ball"
    if value == "service":
        return "service"
    if value == "clearance":
        return "clearance"
    return "shot"


PASS_INTENT_MAP = {
    "safe recycle": "safe_recycle",
    "line breaking": "line_breaking",
    "switch of play": "switch_of_play",
    "through ball": "through_ball",
    "service into box": "service_into_box",
}


def _extract_intent_and_outcome(tail: str) -> Tuple[Optional[str], str]:
    cleaned = tail.strip()
    comma_index = cleaned.find(",")
    if comma_index == -1:
        for phrase, mapped in PASS_INTENT_MAP.items():
            if cleaned.startswith(phrase):
                remainder = cleaned[len(phrase) :].strip(" ,")
                return mapped, remainder
        return None, cleaned

    potential_intent = cleaned[:comma_index].strip().lower()
    mapped_intent = _match_intent_phrase(potential_intent)
    if mapped_intent:
        remainder = cleaned[comma_index + 1 :].strip()
        return mapped_intent, remainder
    return None, cleaned


def _match_intent_phrase(value: str) -> Optional[str]:
    for phrase, mapped in PASS_INTENT_MAP.items():
        if value.startswith(phrase):
            return mapped
    return None


def _parse_on_ball_outcome(clause: str, action_type: str) -> Dict[str, str]:
    clause = clause.strip()
    clause_lower = clause.lower()

    completion_to_match = re.match(r"^to\s+(?P<target>.+)\s+completed\.?$", clause_lower)
    if completion_to_match:
        return {
            "action_outcome_team": "same_team",
            "action_outcome_detail": "completed",
            "next_possession_team": "same_team",
        }

    if COMPLETED_RE.match(clause):
        return {
            "action_outcome_team": "same_team",
            "action_outcome_detail": "completed",
            "next_possession_team": "same_team",
        }

    if TO_OPPONENT_RE.match(clause):
        return {
            "action_outcome_team": "opponent",
            "action_outcome_detail": "intercepted",
            "next_possession_team": "opponent",
        }

    out_match = OUT_FOR_RE.match(clause)
    if out_match:
        restart = out_match.group("restart")
        next_team = "opponent" if restart in {"goal kick", "corner"} else "same_team"
        detail = "clearance_out" if action_type == "clearance" else "overhit"
        return {
            "action_outcome_team": "out_of_play",
            "action_outcome_detail": detail,
            "next_possession_team": next_team,
        }

    if BLOCKED_RE.match(clause):
        detail = "shot_blocked" if action_type == "shot" else "blocked"
        return {
            "action_outcome_team": "loose",
            "action_outcome_detail": detail,
            "next_possession_team": "contested",
        }

    if "on target" in clause_lower:
        return {
            "action_outcome_team": "opponent",
            "action_outcome_detail": "shot_on_target",
            "next_possession_team": "opponent",
        }

    if "off target" in clause_lower:
        return {
            "action_outcome_team": "out_of_play",
            "action_outcome_detail": "shot_off_target",
            "next_possession_team": "opponent",
        }

    return {
        "action_outcome_team": "loose",
        "action_outcome_detail": "blocked",
        "next_possession_team": "contested",
    }


def _map_post_loss_behaviour(value: str) -> str:
    if value == "immediate press":
        return "immediate_press"
    if value == "track runner":
        return "track_runner"
    if value == "token pressure":
        return "token_pressure"
    return "no_reaction"


def _map_post_loss_outcome(value: str) -> str:
    if value.startswith("wins it back herself"):
        return "won_back_possession_self"
    if value.startswith("wins it back for the team"):
        return "won_back_possession_team"
    if value.startswith("forces error"):
        return "forced_error_only"
    if value.startswith("no effect"):
        return "no_effect"
    if value.startswith("negative effect"):
        return "negative_effect"
    return "no_effect"


def _normalize_player(token: str) -> str:
    lookup = token.strip().lower()
    return SPOKEN_NUMBER_MAP.get(lookup, token)


def _build_base_event(
    state: ParserState,
    segment: Segment,
    *,
    team: str,
    player_number: str,
    event_type: str,
    source_phrase: str,
) -> Dict[str, Any]:
    event_id = state.next_event_id()
    return {
        "event_id": event_id,
        "match_id": state.match_id,
        "period": state.period,
        "video_time_s": segment.start + state.offset_seconds,
        "team": team,
        "player_id": None,
        "player_name": None,
        "player_jersey_number": player_number,
        "player_role": None,
        "event_type": event_type,
        "possession_id": None,
        "sequence_id": None,
        "source_phrase": source_phrase,
        "zone_start": None,
        "zone_end": None,
        "tags": None,
        "comment": None,
    }


def _split_segment_text(text: str) -> List[str]:
    if not text:
        return []
    stripped = text.strip()
    if not stripped:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", stripped)
    fragments: List[str] = []
    connectors = (
        "through ball",
        "completed to",
        "intercepted",
        "wins it back",
        "safe recycle",
        "line breaking",
        "switch of play",
        "service into box",
        "token pressure",
        "immediate press",
        "track runner",
        "no effect",
        "negative effect",
        "on target",
        "off target",
        "blocked",
        "out for",
    )
    for candidate in sentences:
        cleaned = candidate.strip()
        if not cleaned:
            continue
        lower = cleaned.lower()
        if fragments and lower.startswith(connectors):
            fragments[-1] = f"{fragments[-1].rstrip('. ')} {cleaned}"
        else:
            fragments.append(cleaned)
    return fragments


def _normalize_phrase(text: str) -> str:
    normalized = text.lower()
    normalized = normalized.replace("–", "-")
    normalized = re.sub(r"[,:;]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.strip(" .!?")
    normalized = re.sub(r"\bone\s+touch\b", "one-touch", normalized)
    normalized = re.sub(r"\btwo\s+touch\b", "two-touch", normalized)
    normalized = re.sub(r"\bthree\s+plus\s+touch\b", "three-plus-touch", normalized)
    normalized = re.sub(r"\bcarry\s+pass\b", "carry then pass", normalized)
    return normalized.strip()


__all__ = ["parse_transcript_segments"]
