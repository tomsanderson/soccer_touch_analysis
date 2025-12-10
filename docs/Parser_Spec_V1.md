# Parser Spec V1 – Soccer Touch Analysis

**File:** `docs/Parser_Spec_V1.md`  
**Schema:** `Schema_V1.md`  
**Grammar:** `Grammar_V1.md`  

**Goal:** Define how to convert narrated transcript lines into `Schema_V1` events using `Grammar_V1`, with explicit regex-style patterns and field mappings.

This spec is written with Python-style regex and parsing in mind, but the logic is language-agnostic.

---

## 1. Input Format Assumptions

### 1.1 Transcript Structure

The transcription step yields a list of segments, each with:

- `start` – start time in seconds from the beginning of the recording (float)  
- `end` – end time in seconds (float)  
- `text` – transcribed text (string)

Example JSON-ish structure:

    [
      { "start": 2.1, "end": 3.5, "text": "First half, zero minutes, Blue in yellow, White in black, kickoff." },
      { "start": 10.2, "end": 11.0, "text": "Blue seven first touch high, controlled." },
      { "start": 13.5, "end": 15.2, "text": "Blue seven two-touch pass, safe recycle to center back, completed." },
      { "start": 17.0, "end": 18.5, "text": "After losing it, Blue seven immediate press, wins it back herself." }
    ]

### 1.2 Video Time Alignment

- Default assumption: `video_time_s ≈ audio_segment.start + constant_offset`.
- For V1, treat `offset = 0` by default (start recording and video together, or accept small error).
- Later versions can:
  - Detect phrases like `First half, zero minutes` or `Mark, ten minutes` to compute a more precise offset.

In this spec, `video_time_s` should be computed as:

    video_time_s = segment["start"] + offset_seconds

---

## 2. Event Construction Overview

For each transcript segment:

1. Normalize text:
   - Lowercase.
   - Strip surrounding whitespace.
2. Decide which template it matches:
   - Template 1 – First Touch  
   - Template 2 – On-Ball Action  
   - Template 3 – Post-Loss Reaction  
   - Or ignore if not recognized (e.g., markers like “First half, zero minutes”).
3. Apply regex to extract fields.
4. Build an event dict matching `Schema_V1`, including:
   - Core fields (event_id, match_id, period, video_time_s, team, etc.).
   - Template-specific fields.
5. Track:
   - `last_loss_event_id` (for `post_loss_reaction.trigger_event_id`).
   - `possession_id` (optional V1: can be a running counter per half).

---

## 3. Regex Patterns (Python-Style)

Assumptions:

- All regexes use `re.IGNORECASE`.
- The line is stripped before matching.

### 3.1 Helper Pattern – Team + Player

Regex (conceptual):

    (?P<team>Blue|White)\s+(?P<player>[A-Za-z0-9]+)

Mapping:

- `team` → `"Blue"` / `"White"` after `.capitalize()`.  
- `player` → jersey number or short name (e.g., `"seven"`, `"10"`, `"Tegan"`).  
- Mapping from spoken `"seven"` to `"7"` should be done in a `normalize_player()` helper.

---

## 4. Template 1 – First Touch

### 4.1 Expected Spoken Form

    [team] [player] first touch [quality], [result].

Examples:

- `Blue seven first touch high, controlled.`  
- `Blue seven first touch medium, rebound free space.`  
- `Blue seven first touch low, rebound to opponent.`  

### 4.2 Regex Pattern

Python-style:

    FIRST_TOUCH_RE = re.compile(
        r'^(?P<team>Blue|White)\s+'
        r'(?P<player>[A-Za-z0-9]+)\s+'
        r'first touch\s+'
        r'(?P<quality>high|medium|low)\s*,\s*'
        r'(?P<result>controlled|rebound free space|rebound to opponent)\.?$',
        re.IGNORECASE
    )

### 4.3 Field Mapping (Schema_V1)

Given a segment `seg` and match context (`match_id`, `period`, `offset`):

Core:

- `event_type` = `"first_touch"`  
- `video_time_s` = `seg["start"] + offset`

Template-specific:

    team_raw = m.group("team")
    player_raw = m.group("player")
    quality_raw = m.group("quality").lower()
    result_text = m.group("result").lower()

Mapping:

    team = team_raw.capitalize()  # "Blue" or "White"
    player_jersey_number = normalize_player(player_raw)  # e.g. "seven" -> "7"
    first_touch_quality = quality_raw  # "high" | "medium" | "low"

Derive result + possession:

    if result_text == "controlled":
        first_touch_result = "controlled"
        possession_after_touch = "same_player"
    elif result_text == "rebound free space":
        first_touch_result = "rebound_free_space"
        possession_after_touch = "loose"
    else:  # "rebound to opponent"
        first_touch_result = "rebound_opponent"
        possession_after_touch = "opponent"

Then:

- `first_touch_result` = `"controlled" | "rebound_free_space" | "rebound_opponent"`  
- `possession_after_touch` = `"same_player" | "same_team_other_player" | "opponent" | "loose"`  
- `maintained_possession_bool` = `possession_after_touch in ("same_player", "same_team_other_player")`  
- `source_phrase` = original (non-lowercased) segment text

---

## 5. Template 2 – On-Ball Action

### 5.1 Expected Spoken Form

    [team] [player] [touch-count]-touch [action] [optional intent], [outcome phrase].

Where:

- `[touch-count]` = `one` / `two` / `three-plus`  
- `[action]` = `pass` / `forward ball` / `service` / `clearance` / `shot`  
- `[optional intent]` = `safe recycle` / `line breaking` / `switch of play` / `through ball` / `service into box` (optional)  
- `[outcome phrase]` describes result.

Examples:

- `Blue seven two-touch pass, safe recycle to center back, completed.`  
- `Blue seven one-touch through ball to Blue nine, intercepted by opponent.`  
- `Blue four three-plus-touch clearance, pure clearance out for throw.`  
- `Blue eleven one-touch service into box, completed to Blue nine.`  
- `Blue seven one-touch shot from edge of box, on target, saved.`  

### 5.2 Regex Pattern (Core)

    ON_BALL_RE = re.compile(
        r'^(?P<team>Blue|White)\s+'
        r'(?P<player>[A-Za-z0-9]+)\s+'
        r'(?P<touch_count>one|two|three-plus)-touch\s+'
        r'(?P<action>pass|forward ball|service|clearance|shot)'
        r'(?:\s+(?P<intent>safe recycle|line breaking|switch of play|through ball|service into box))?'
        r'\s*,\s*(?P<outcome_clause>.+)$',
        re.IGNORECASE
    )

Anything after the first comma is `outcome_clause`, which is parsed further.

### 5.3 Mapping – Touch Count and Action Type

    tc = m.group("touch_count").lower()
    if tc == "one":
        touch_count_before_action = "one_touch"
    elif tc == "two":
        touch_count_before_action = "two_touch"
    else:
        touch_count_before_action = "three_plus"

    action_raw = m.group("action").lower()

    if action_raw == "pass":
        on_ball_action_type = "pass"
    elif action_raw == "forward ball":
        on_ball_action_type = "forward_ball"
    elif action_raw == "service":
        on_ball_action_type = "service"
    elif action_raw == "clearance":
        on_ball_action_type = "clearance"
    else:
        on_ball_action_type = "shot"

Intent mapping:

    intent_raw = m.group("intent")
    if intent_raw is None:
        pass_intent = None
    else:
        intent_raw = intent_raw.lower()
        mapping = {
            "safe recycle": "safe_recycle",
            "line breaking": "line_breaking",
            "switch of play": "switch_of_play",
            "through ball": "through_ball",
            "service into box": "service_into_box",
        }
        pass_intent = mapping.get(intent_raw, "other")

### 5.4 Outcome Clause Parsing

`outcome_clause` examples:

- `completed.`  
- `completed to center back.`  
- `to opponent.`  
- `intercepted by opponent.`  
- `out for throw.`  
- `out for goal kick.`  
- `out for corner.`  
- `blocked.`  
- `on target, saved.`  
- `off target.`  

Suggested patterns:

Completed:

    COMPLETED_RE = re.compile(
        r'^completed(?:\s+to\s+(?P<target>.+))?\.?$',
        re.IGNORECASE
    )

If matched:

- `action_outcome_team` = `"same_team"`  
- `action_outcome_detail` = `"completed"`  
- `next_possession_team` = `"same_team"`

To opponent / intercepted:

    TO_OPPONENT_RE = re.compile(
        r'^(?:to\s+opponent|intercepted(?:\s+by\s+opponent)?)\.?$',
        re.IGNORECASE
    )

If matched:

- `action_outcome_team` = `"opponent"`  
- `action_outcome_detail` = `"intercepted"`  
- `next_possession_team` = `"opponent"`

Out of play:

    OUT_FOR_RE = re.compile(
        r'^out\s+for\s+(?P<restart>throw|goal kick|corner)\.?$',
        re.IGNORECASE
    )

If matched:

- `action_outcome_team` = `"out_of_play"`  
- `action_outcome_detail` = `"clearance_out"` or `"overhit"` depending on context  
- `next_possession_team` can be inferred (e.g. `"same_team"` for throw; `"opponent"` for goal kick/corner) or left for later refinement.

Blocked:

    BLOCKED_RE = re.compile(
        r'^blocked\.?$',
        re.IGNORECASE
    )

If matched:

- If `on_ball_action_type == "shot"`:
        `action_outcome_detail` = `"shot_blocked"`
- Else:
        `action_outcome_detail` = `"blocked"`

Shot on target / off target:

    clause_lower = outcome_clause.lower()
    if "on target" in clause_lower:
        action_outcome_detail = "shot_on_target"
        # action_outcome_team / next_possession_team: choose V1 behaviour (e.g. opponent or out_of_play)
    elif "off target" in clause_lower:
        action_outcome_detail = "shot_off_target"
        action_outcome_team = "out_of_play"

If none match, V1 can default to a generic outcome or mark as unknown and improve later.

### 5.5 Assembled On-Ball Event

For an `on_ball_action` event, populate:

- `event_type` = `"on_ball_action"`  
- `team`, `player_jersey_number`  
- `touch_count_before_action`  
- `on_ball_action_type`  
- `carry_flag` (V1: default `False`, unless a later rule sets it)  
- `pass_intent`  
- `action_outcome_team`  
- `action_outcome_detail`  
- `next_possession_team`  
- `source_phrase` = original text  

Core fields (`event_id`, `match_id`, `period`, `video_time_s`) come from calling context.

---

## 6. Template 3 – Post-Loss Reaction

### 6.1 Expected Spoken Form

    After losing it, [team] [player] [behaviour phrase], [outcome phrase].

Examples:

- `After losing it, Blue seven immediate press, wins it back herself.`  
- `After losing it, Blue seven track runner, wins it back for the team.`  
- `After losing it, Blue seven token pressure, no effect.`  
- `After losing it, Blue seven stops and watches, negative effect.`  

### 6.2 Regex Pattern

    POST_LOSS_RE = re.compile(
        r'^after losing it,\s*'
        r'(?P<team>Blue|White)\s+'
        r'(?P<player>[A-Za-z0-9]+)\s+'
        r'(?P<behaviour>immediate press|track runner|token pressure|stops and watches|gives up)\s*,\s*'
        r'(?P<outcome_clause>.+)$',
        re.IGNORECASE
    )

### 6.3 Behaviour Mapping

    behaviour_raw = m.group("behaviour").lower()
    if behaviour_raw == "immediate press":
        post_loss_behaviour = "immediate_press"
    elif behaviour_raw == "track runner":
        post_loss_behaviour = "track_runner"
    elif behaviour_raw == "token pressure":
        post_loss_behaviour = "token_pressure"
    else:  # "stops and watches" or "gives up"
        post_loss_behaviour = "no_reaction"

### 6.4 Outcome Clause Mapping

Outcome clause examples:

- `wins it back herself.`  
- `wins it back for the team.`  
- `forces error, but no win.`  
- `no effect.`  
- `negative effect.`  

Mapping:

    oc = outcome_clause.strip().lower()
    if oc.startswith("wins it back herself"):
        post_loss_outcome = "won_back_possession_self"
    elif oc.startswith("wins it back for the team"):
        post_loss_outcome = "won_back_possession_team"
    elif oc.startswith("forces error"):
        post_loss_outcome = "forced_error_only"
    elif oc.startswith("no effect"):
        post_loss_outcome = "no_effect"
    elif oc.startswith("negative effect"):
        post_loss_outcome = "negative_effect"
    else:
        post_loss_outcome = "no_effect"  # fallback

### 6.5 Effort Intensity Heuristic

Optional heuristic for V1:

    if post_loss_behaviour in ("immediate_press", "track_runner"):
        post_loss_effort_intensity = "high"
    elif post_loss_behaviour == "token_pressure":
        post_loss_effort_intensity = "medium"
    else:
        post_loss_effort_intensity = "low"

### 6.6 Assembled Post-Loss Event

For a `post_loss_reaction` event, populate:

- `event_type` = `"post_loss_reaction"`  
- `team`, `player_jersey_number`  
- `post_loss_behaviour`  
- `post_loss_outcome`  
- `post_loss_effort_intensity`  
- `trigger_event_id` = event_id of the last event where your team lost possession  
- `source_phrase` = original text  

Core fields (`match_id`, `period`, `video_time_s`, etc.) come from context.

---

## 7. Event Routing & Control Flow

### 7.1 Event Type Detection Order

For each segment (line of transcript):

1. Try `FIRST_TOUCH_RE`.  
2. Else try `ON_BALL_RE`.  
3. Else try `POST_LOSS_RE`.  
4. Else:
   - If it matches marker phrases (e.g., `First half, zero minutes`, `Mark, ten minutes`), use for alignment only.
   - Otherwise, ignore or store as a non-event note.

### 7.2 Tracking Last-Loss Event

Maintain:

    last_loss_event_id: Optional[str] = None

Conditions for updating `last_loss_event_id`:

- For `first_touch` events:
  - If `maintained_possession_bool == False` and `possession_after_touch == "opponent"`.
- For `on_ball_action` events:
  - If `action_outcome_team == "opponent"`.

When such an event is created:

    last_loss_event_id = current_event_id

When creating a `post_loss_reaction` event:

- `trigger_event_id = last_loss_event_id` if not `None`.

If `last_loss_event_id` is `None`, leave `trigger_event_id` empty or null.

### 7.3 Possession IDs (V1 Approximation)

Use a simple possession
