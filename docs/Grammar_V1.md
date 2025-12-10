# Soccer Touch Analysis – Spoken Grammar V1

**Version:** 1.0  
**Purpose:** Define the constrained spoken “mini-language” used during video narration so transcripts can be parsed into the **Schema V1** event model.

The grammar centers on three **templates**:

1. First Touch  
2. On-Ball Action  
3. Post-Loss Reaction  

Analysts should aim to speak these patterns clearly and consistently while watching a match (live or replay).

---

## 1. General Conventions

- Identify players as:  
  - `[team] [player]`  
  - Example: `Blue seven`, `White ten`, `Blue Tegan`.
- Use **simple, repeatable phrases** and avoid unnecessary filler words.
- Speak each event as a **separate phrase or sentence**.
- If you need to pause or rewind video, you may optionally note that aloud (e.g., `"Pausing"`, `"Resuming around twelve-thirty"`), but the parser may ignore these.

---

## 2. Template 1 – First Touch

Used when the player makes a **first contact** that you want to code.

### 2.1 Pattern

> `[team] [player] first touch [quality], [result].`

### 2.2 Tokens

- `[team]` – e.g., `Blue`, `White`.  
  (Pick a consistent pair for each match.)
- `[player]` – jersey number or short name, e.g., `seven`, `ten`, `Tegan`.
- `[quality]` – one of:
  - `high`
  - `medium`
  - `low`
- `[result]` – one of:
  - `controlled`
  - `rebound free space`
  - `rebound to opponent`

### 2.3 Examples

- `Blue seven first touch high, controlled.`  
- `Blue seven first touch medium, rebound free space.`  
- `Blue seven first touch low, rebound to opponent.`  

### 2.4 Mapping to Schema

- `first_touch_quality` ← `high` / `medium` / `low`
- `first_touch_result`:
  - `controlled` → `"controlled"`
  - `rebound free space` → `"rebound_free_space"`
  - `rebound to opponent` → `"rebound_opponent"`

Default `possession_after_touch` values (can be overridden later):

- `controlled` → `"same_player"`
- `rebound free space` → `"loose"`
- `rebound to opponent` → `"opponent"`

`maintained_possession_bool` is `true` when `possession_after_touch` is `"same_player"` or `"same_team_other_player"`.

---

## 3. Template 2 – On-Ball Action

Used after a **successful first touch** or any moment when the player clearly has possession and then does something with the ball.

### 3.1 Pattern

> `[team] [player] [touch-count]-touch [action] [optional intent], [outcome phrase].`

You may omit the `[optional intent]` segment if you wish.

### 3.2 Tokens

#### 3.2.1 `[touch-count]`

- `one` → `"one_touch"`
- `two` → `"two_touch"`
- `three-plus` → `"three_plus"`

Example spoken: `two-touch`, `three-plus-touch`.

#### 3.2.2 `[action]` → `on_ball_action_type`

- `pass`
- `forward ball`
- `service`
- `clearance`
- `shot`

Optionally, you can say `"carry then pass"` / `"carry then shot"` to indicate a carry before the action (`carry_flag = true`).

#### 3.2.3 `[optional intent]` (optional)

Maps primarily to `pass_intent`:

- `safe recycle` → `"safe_recycle"`
- `line breaking` → `"line_breaking"`
- `switch of play` → `"switch_of_play"`
- `through ball` → `"through_ball"`
- `service into box` → `"service_into_box"`

You can mix this in naturally, e.g.:

- `two-touch pass, safe recycle to center back`
- `one-touch forward ball, through ball to nine`

#### 3.2.4 `[outcome phrase]`

Determines `action_outcome_team` and `action_outcome_detail` (and sometimes `next_possession_team`).

Common patterns:

- `completed to [teammate/role]`
  - → `action_outcome_team = "same_team"`
  - → `action_outcome_detail = "completed"`

- `to opponent`
  - → `action_outcome_team = "opponent"`
  - → parser may set `"intercepted"` or a simple giveaway.

- `out for [throw/goal kick/corner]`
  - → `action_outcome_team = "out_of_play"`

- `blocked`
  - → `action_outcome_detail = "blocked"`  
  - `action_outcome_team` depends on who wins the ball next.

For shots:

- `on target`
  - → `action_outcome_detail = "shot_on_target"`
- `off target`
  - → `action_outcome_detail = "shot_off_target"`
- `blocked`
  - → `action_outcome_detail = "shot_blocked"`

### 3.3 Examples

- `Blue seven two-touch pass, safe recycle to center back, completed.`  
- `Blue seven one-touch through ball to Blue nine, intercepted by opponent.`  
- `Blue four three-plus-touch clearance, pure clearance out for throw.`  
- `Blue eleven one-touch service into box, completed to Blue nine.`  
- `Blue seven one-touch shot from edge of box, on target, saved.`  

### 3.4 Mapping to Schema (Summary)

- `touch_count_before_action` ← `"one_touch"` / `"two_touch"` / `"three_plus"`.
- `on_ball_action_type` ← `"pass"` / `"forward_ball"` / `"service"` / `"clearance"` / `"shot"`.
- `carry_flag`:
  - `true` if you explicitly say `"carry then …"`, or choose to infer from context.
- `pass_intent` (for pass-like actions) mapped from optional intent phrases.
- `action_outcome_team`, `action_outcome_detail`, `next_possession_team` derived from `[outcome phrase]` and subsequent context.

---

## 4. Template 3 – Post-Loss Reaction

Used immediately after the team loses possession (either on the first touch or on-ball action).

### 4.1 Pattern

> `After losing it, [team] [player] [behaviour phrase], [outcome phrase].`

### 4.2 Tokens

#### 4.2.1 `[behaviour phrase]` → `post_loss_behaviour`

- `immediate press` → `"immediate_press"`
- `track runner` → `"track_runner"`
- `token pressure` → `"token_pressure"`
- `stops and watches` → `"no_reaction"`
- `gives up` → `"no_reaction"`

#### 4.2.2 `[outcome phrase]` → `post_loss_outcome`

- `wins it back herself` → `"won_back_possession_self"`
- `wins it back for the team` → `"won_back_possession_team"`
- `forces error, but no win` → `"forced_error_only"`
- `no effect` → `"no_effect"`
- `negative effect` → `"negative_effect"`

### 4.3 Examples

- `After losing it, Blue seven immediate press, wins it back herself.`  
- `After losing it, Blue seven track runner, wins it back for the team.`  
- `After losing it, Blue seven token pressure, no effect.`  
- `After losing it, Blue seven stops and watches, negative effect.`  

### 4.4 Mapping to Schema

- `post_loss_behaviour` set from `[behaviour phrase]`.
- `post_loss_outcome` set from `[outcome phrase]`.
- `post_loss_effort_intensity` may be inferred:
  - `immediate_press`, `track_runner` → typically `"high"`.
  - `token_pressure` → `"medium"` or `"low"`.
  - `no_reaction` → `"low"`.
- `trigger_event_id` is the `event_id` of the event where possession was lost.

---

## 5. Recording & Sync Notes

These are workflow suggestions that support parsing and time-alignment.

### 5.1 Start-of-Half Marker

At the beginning of each period:

1. Pause video at 0:00.
2. Start recording (e.g., iPhone Voice Memos).
3. Say:

   > `First half, zero minutes, Blue in yellow, White in black, kickoff.`

4. Start video playback.

This lets the app treat that phrase as `video_time_s ≈ 0`.

For the second half:

> `Second half, zero minutes, …`

### 5.2 Optional Time Marks

At approximate 10:00 and 20:00 of video time:

- Say: `Mark, ten minutes.`  
- Say: `Mark, twenty minutes.`  

This provides additional alignment points if needed.

---

## 6. Practical Tips for the Analyst

- Don’t worry about perfect wording; focus on using the **key phrases**:
  - `first touch`, `high/medium/low`, `controlled/rebound free space/rebound to opponent`
  - `one-touch/two-touch/three-plus-touch`
  - `pass/forward ball/service/clearance/shot`
  - `safe recycle/line breaking/switch of play/through ball/service into box`
  - `completed/to opponent/out for [restart]/blocked`
  - `After losing it, … immediate press/track runner/token pressure/stops and watches`
- Short, clipped sentences are easier to parse than long, flowing commentary.
- You can always pause and rewind the video if the action is too fast; just resume using the same templates.

---

## 7. Versioning Notes

- This document defines **Grammar V1**.
- Any changes to the spoken templates or allowed phrases should:
  - Be captured in `Grammar_V2.md` (and higher).
  - Maintain clear mapping to Schema versions (e.g., Schema V2, Grammar V2).
