# Parser Spec V1 – Soccer Touch Analysis

**File:** `docs/Parser_Spec_V1.md`  
**Schema:** `Schema_V1.md`  
**Grammar:** `Grammar_V1.md`  

**Goal:** Define how to convert narrated transcript lines into `Schema_V1` events using `Grammar_V1`, with explicit regex-style patterns and field mappings.

This spec is written with **Python-style regex** and parsing in mind, but the logic is language-agnostic.

---

## 1. Input Format Assumptions

### 1.1 Transcript Structure

The transcription step yields a list of segments, each with:

- `start` – start time in seconds from the beginning of the recording (float)  
- `end` – end time in seconds (float)  
- `text` – transcribed text (string)

Example JSON-ish structure:

```json
[
  { "start": 2.1, "end": 3.5, "text": "First half, zero minutes, Blue in yellow, White in black, kickoff." },
  { "start": 10.2, "end": 11.0, "text": "Blue seven first touch high, controlled." },
  { "start": 13.5, "end": 15.2, "text": "Blue seven two-touch pass, safe recycle to center back, completed." },
  { "start": 17.0, "end": 18.5, "text": "After losing it, Blue seven immediate press, wins it back herself." }
]
```

### 1.2 Video Time Alignment

- **Default assumption:** `video_time_s ≈ audio_segment.start + constant_offset`.
- For V1, treat **offset = 0** by default (start recording and video together, or accept small error).
- Later versions can:
  - Detect phrases like `First half, zero minutes` or `Mark, ten minutes` to compute a more precise offset.

In this spec, `video_time_s` should be computed as:

```python
video_time_s = segment["start"] + offset_seconds
```

---

## 2. Event Construction Overview

For each transcript segment:

1. Normalize text:
   - Lowercase.
   - Strip surrounding whitespace.
2. Decide which **template** it matches:
   - Template 1 – First Touch  
   - Template 2 – On-Ball Action  
   - Template 3 – Post-Loss Reaction  
   - Or ignore if not recognized (e.g., markers like “First half, zero minutes”).
3. Apply **regex** to extract fields.
4. Build an `Event` dict matching `Schema_V1`, including:
   - Core fields (event_id, match_id, period, video_time_s, team, etc.).
   - Template-specific fields.
5. Track:
   - `last_loss_event_id` (for `post_loss_reaction.trigger_event_id`).
   - `possession_id` (optional V1: can be simplified to a running counter per half).

---

## 3. Regex Patterns (Python-Style)

All regexes are assumed to have:

- `re.IGNORECASE`
- Optional surrounding whitespace ignored by pre-strip.

### 3.1 Helpers

**Team + Player pattern**

```regex
(?P<team>Blue|White)\s+(?P<player>[A-Za-z0-9]+)
```

- `team` → `"Blue"` / `"White"` after `.capitalize()`.  
- `player` → jersey number or short name (e.g., `"seven"`, `"10"`, `"Tegan"`).  
  Mapping from spoken `"seven"` to jersey `"7"` should be handled in a separate normalization map.

---

## 4. Template 1 – First Touch

### 4.1 Expected Spoken Form

> `[team] [player] first touch [quality], [result].`

Examples:

- `Blue seven first touch high, controlled.`  
- `Blue seven first touch medium, rebound free space.`  
- `Blue seven first touch low, rebound to opponent.`  

### 4.2 Regex Pattern

```python
FIRST_TOUCH_RE = re.compile(
    r'^(?P<team>Blue|White)\s+'
    r'(?P<player>[A-Za-z0-9]+)\s+'
    r'first touch\s+'
    r'(?P<quality>high|medium|low)\s*,\s*'
    r'(?P<result>controlled|rebound free space|rebound to opponent)\.?$',
    re.IGNORECASE
)
```

### 4.3 Field Mapping (Schema_V1)

Given a segment `seg` and match context (match_id, period, offset):

**Core**

- `event_type` = `"first_touch"`  
- `video_time_s` = `seg["start"] + offset`

Other core fields (`event_id`, `match_id`, `period`, etc.) come from context.

**Template fields**

From regex groups:

```python
team_raw = m.group("team")
player_raw = m.group("player")
quality_raw = m.group("quality").lower()
result_text = m.group("result").lower()
```

Mapping:

```python
team = team_raw.capitalize()  # "Blue" or "White"
player_jersey_number = normalize_player(player_raw)  # e.g. "seven" -> "7"
first_touch_quality = quality_raw  # "high" | "medium" | "low"
```

Derive:

```python
if result_text == "controlled":
    first_touch_result = "controlled"
    possession_after_touch = "same_player"
elif result_text == "rebound free space":
    first_touch_result = "rebound_free_space"
    possession_after_touch = "loose"
else:  # "rebound to opponent"
    first_touch_result = "rebound_opponent"
    possession_after_touch = "opponent"
```

Then:

- `first_touch_result` = `first_touch_result`  
- `possession_after_touch` = `possession_after_touch`  
- `maintained_possession_bool` = `possession_after_touch in ("same_player", "same_team_other_player")`  
- `source_phrase` = original (non-lowercased) segment text

---

## 5. Template 2 – On-Ball Action

### 5.1 Expected Spoken Form

> `[team] [player] [touch-count]-touch [action] [optional intent], [outcome phrase].`

Where:

- `[touch-count]` = `one` / `two` / `three-plus`  
- `[action]` = `pass` / `forward ball` / `service` / `clearance` / `shot`  
- `[optional intent]` = `safe recycle` / `line breaking` / `switch of play` / `through ball` / `service into box` (optional)  
- `[outcome phrase]` has a few supported forms (see below).

Examples:

- `Blue seven two-touch pass, safe recycle to center back, completed.`  
- `Blue seven one-touch through ball to Blue nine, intercepted by opponent.`  
- `Blue four three-plus-touch clearance, pure clearance out for throw.`  
- `Blue eleven one-touch service into box, completed to Blue nine.`  
- `Blue seven one-touch shot from edge of box, on target, saved.`  

### 5.2 Regex Pattern (Core)

We break on the comma to simplify parsing:

```python
ON_BALL_RE = re.compile(
    r'^(?P<team>Blue|White)\s+'
    r'(?P<player>[A-Za-z0-9]+)\s+'
    r'(?P<touch_count>one|two|three-plus)-touch\s+'
    r'(?P<action>pass|forward ball|service|clearance|shot)'
    r'(?:\s+(?P<intent>safe recycle|line breaking|switch of play|through ball|service into box))?'
    r'\s*,\s*(?P<outcome_clause>.+)$',
    re.IGNORECASE
)
```

Anything after the first comma is captured as `outcome_clause` and further parsed by simpler regexes or string matching.

### 5.3 Mapping – Touch Count and Action Type

From groups:

```python
tc = m.group("touch_count").lower()
if tc == "one":
    touch_count_before_action = "one_touch"
elif tc == "two":
    touch_count_before_action = "two_touch"
else:
    touch_count_before_action = "three_plus"

action_raw = m.group("action").lower()  # "pass", "forward ball", etc.

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
```

Intent:

```python
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
```

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

For shots:

- `on target, saved.`  
- `off target.`  
- `blocked.`  

Use one or more simple regexes / `if` checks in order of specificity.

#### 5.4.1 Completed to same team

```python
COMPLETED_RE = re.compile(
    r'^completed(?:\s+to\s+(?P<target>.+))?\.?$',
    re.IGNORECASE
)
```

If this matches:

- `action_outcome_team` = `"same_team"`  
- `action_outcome_detail` = `"completed"`  
- `next_possession_team` = `"same_team"`

#### 5.4.2 To opponent / intercepted

```python
TO_OPPONENT_RE = re.compile(
    r'^(?:to\s+opponent|intercepted(?:\s+by\s+opponent)?)\.?$',
    re.IGNORECASE
)
```

If this matches:

- `action_outcome_team` = `"opponent"`  
- `action_outcome_detail` = `"intercepted"` (or `"completed"` giveaway if you want a second category)
- `next_possession_team` = `"opponent"`

#### 5.4.3 Out of play

```python
OUT_FOR_RE = re.compile(
    r'^out\s+for\s+(?P<restart>throw|goal kick|corner)\.?$',
    re.IGNORECASE
)
```

If this matches:

- `action_outcome_team` = `"out_of_play"`  
- `action_outcome_detail` = `"clearance_out"` or `"overhit"` depending on `on_ball_action_type`.
- `next_possession_team` may need manual logic (e.g., `"same_team"` for throw, `"opponent"` for goal kick/corner), depending on restart.

#### 5.4.4 Blocked

```python
BLOCKED_RE = re.compile(
    r'^blocked\.?$',
    re.IGNORECASE
)
```

If this matches:

- If `on_ball_action_type == "shot"`:
  - `action_outcome_detail` = `"shot_blocked"`
- Else:
  - `action_outcome_detail` = `"blocked"`

`action_outcome_team` and `next_possession_team` may default to `"loose"`.

#### 5.4.5 Shot on target / off target

Simple substring checks:

```python
clause_lower = outcome_clause.lower()
if "on target" in clause_lower:
    action_outcome_detail = "shot_on_target"
    # next_possession_team depends on how you want to treat rebounds; V1 can default to "opponent" or "out_of_play"
elif "off target" in clause_lower:
    action_outcome_detail = "shot_off_target"
    action_outcome_team = "out_of_play"
```

### 5.5 Assembled `on_ball_action` Event

Populate:

- `event_type` = `"on_ball_action"`  
- `touch_count_before_action`  
- `on_ball_action_type`  
- `carry_flag` (V1: default `False`, or an additional rule if you add “carry then” detection)  
- `pass_intent`  
- `action_outcome_team`  
- `action_outcome_detail`  
- `next_possession_team`  
- `source_phrase` = original text

Core fields (`team`, `player_jersey_number`, `video_time_s`, etc.) filled from context and regex groups.

---

## 6. Template 3 – Post-Loss Reaction

### 6.1 Expected Spoken Form

> `After losing it, [team] [player] [behaviour phrase], [outcome phrase].`

Examples:

- `After losing it, Blue seven immediate press, wins it back herself.`  
- `After losing it, Blue seven track runner, wins it back for the team.`  
- `After losing it, Blue seven token pressure, no effect.`  
- `After losing it, Blue seven stops and watches, negative effect.`  

### 6.2 Regex Pattern

```python
POST_LOSS_RE = re.compile(
    r'^after losing it,\s*'
    r'(?P<team>Blue|White)\s+'
    r'(?P<player>[A-Za-z0-9]+)\s+'
    r'(?P<behaviour>immediate press|track runner|token pressure|stops and watches|gives up)\s*,\s*'
    r'(?P<outcome_clause>.+)$',
    re.IGNORECASE
)
```

### 6.3 Behaviour Mapping

```python
behaviour_raw = m.group("behaviour").lower()
if behaviour_raw == "immediate press":
    post_loss_behaviour = "immediate_press"
elif behaviour_raw == "track runner":
    post_loss_behaviour = "track_runner"
elif behaviour_raw == "token pressure":
    post_loss_behaviour = "token_pressure"
else:  # "stops and watches" or "gives up"
    post_loss_behaviour = "no_reaction"
```

### 6.4 Outcome Clause Mapping

`outcome_clause` examples:

- `wins it back herself.`  
- `wins it back for the team.`  
- `forces error, but no win.`  
- `no effect.`  
- `negative effect.`  

Mapping:

```python
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
```

### 6.5 Effort Intensity Heuristic

Optional V1 heuristic:

```python
if post_loss_behaviour in ("immediate_press", "track_runner"):
    post_loss_effort_intensity = "high"
elif post_loss_behaviour == "token_pressure":
    post_loss_effort_intensity = "medium"
else:
    post_loss_effort_intensity = "low"
```

### 6.6 Assembled `post_loss_reaction` Event

Populate:

- `event_type` = `"post_loss_reaction"`  
- `team`, `player_jersey_number` from regex groups  
- `post_loss_behaviour`  
- `post_loss_outcome`  
- `post_loss_effort_intensity`  
- `trigger_event_id` – ID of the most recent event where your team lost possession
- `source_phrase` = original text  

Core fields (match_id, period, video_time_s, etc.) are filled from context.

---

## 7. Event Routing & Control Flow

### 7.1 Event Type Detection Order

For each transcript segment (line):

1. Try `FIRST_TOUCH_RE`.  
2. Else try `ON_BALL_RE`.  
3. Else try `POST_LOSS_RE`.  
4. Else:
   - If it matches a **marker** pattern (e.g., `First half, zero minutes`, `Mark, ten minutes`), use it only for alignment/offset.
   - Otherwise, ignore or log as a non-event.

### 7.2 Tracking Last-Loss Event

Maintain:

```python
last_loss_event_id: Optional[str] = None
```

On any event where:

- `event_type == "first_touch"` and `maintained_possession_bool == False`, or  
- `event_type == "on_ball_action"` and `action_outcome_team == "opponent"`,  

update:

```python
last_loss_event_id = current_event_id
```

When building a `post_loss_reaction` event:

- `trigger_event_id = last_loss_event_id` (if not `None`).

If `last_loss_event_id` is `None`, leave `trigger_event_id` empty or null.

### 7.3 Possession IDs (V1 Simplification)

V1 can use a simple possession ID per half:

- Initialize `current_possession_id = 1`.
- When you see a **new first touch for your team** after a previous possession ended, increment:

```python
current_possession_id += 1
```

Conditions for possession ending (approximate):

- `event_type == "first_touch"` with `maintained_possession_bool == False` and `possession_after_touch == "opponent"`, or  
- `event_type == "on_ball_action"` where `action_outcome_team == "opponent"` or `action_outcome_team == "out_of_play"` with restart belonging to opponent.

Assign:

- `possession_id = str(current_possession_id)` to all subsequent events until the next possession end.

This is intentionally approximate for V1.

---

## 8. Testing Suggestions

Create unit tests in `backend/tests/test_parser.py` with sample lines and expected event dicts.

### 8.1 First Touch Test

Input line:

```text
"Blue seven first touch high, controlled."
```

Key expected fields:

```python
{
  "event_type": "first_touch",
  "team": "Blue",
  "player_jersey_number": "7",  # if "seven" → "7"
  "first_touch_quality": "high",
  "first_touch_result": "controlled",
  "possession_after_touch": "same_player",
  "maintained_possession_bool": True,
}
```

### 8.2 On-Ball Action Test

Input line:

```text
"Blue seven two-touch pass, safe recycle to center back, completed."
```

Key expected fields:

```python
{
  "event_type": "on_ball_action",
  "team": "Blue",
  "player_jersey_number": "7",
  "touch_count_before_action": "two_touch",
  "on_ball_action_type": "pass",
  "pass_intent": "safe_recycle",
  "action_outcome_team": "same_team",
  "action_outcome_detail": "completed",
}
```

### 8.3 Post-Loss Reaction Test

Input line:

```text
"After losing it, Blue seven immediate press, wins it back herself."
```

Key expected fields:

```python
{
  "event_type": "post_loss_reaction",
  "team": "Blue",
  "player_jersey_number": "7",
  "post_loss_behaviour": "immediate_press",
  "post_loss_outcome": "won_back_possession_self",
  "post_loss_effort_intensity": "high",
}
```

---

## 9. Versioning

This document is **Parser Spec V1**, aligned with:

- `Schema_V1.md`  
- `Grammar_V1.md`  

Any changes to regex patterns, event routing, or field mapping should be documented in a new file (e.g., `Parser_Spec_V2.md`) and kept in sync with corresponding schema/grammar versions.
