# Soccer Touch Analysis – Schema V1

**Version:** 1.0  
**Scope:** Per-event data model for narrated soccer video analysis, inspired by StatsBomb-style event data.  
**Primary focus:**  
- First-touch quality & outcome  
- On-ball actions from possession  
- Post-loss reactions  

Each **row = one event**.

---

## 1. Event Types (V1)

V1 defines three primary event types:

- `first_touch`
- `on_ball_action`
- `post_loss_reaction`

Additional types (e.g., `ball_recovery`, `carry_only`) may be added in later versions.

---

## 2. Core Fields (All Events)

These fields appear on **every** event row:

| Field                  | Type      | Description                                                                 |
|------------------------|-----------|-----------------------------------------------------------------------------|
| `event_id`             | string    | Unique ID per row (UUID or numeric string).                                |
| `match_id`             | string    | Identifier for the match.                                                  |
| `period`               | string    | Match period: `"1"`, `"2"`, `"ET1"`, `"ET2"`, etc.                          |
| `video_time_s`         | float     | Seconds from the start of the period.                                      |
| `team`                 | string    | Team label (e.g., `"Blue"`, `"White"`).                                     |
| `player_id`            | string    | Internal player identifier.                                                |
| `player_name`          | string    | Human-readable player name.                                                |
| `player_jersey_number` | string    | Jersey number (string or int; stored as string for flexibility).          |
| `player_role`          | string?   | Optional role, e.g., `"CM"`, `"RB"`, `"LW"`.                               |
| `event_type`           | string    | One of: `"first_touch"`, `"on_ball_action"`, `"post_loss_reaction"`.       |
| `possession_id`        | string?   | ID for the possession this event belongs to (approximate allowed in V1).   |
| `sequence_id`          | string?   | Sub-sequence within a possession (can equal `possession_id` in V1).        |
| `source_phrase`        | string    | Raw (or lightly cleaned) transcript phrase that produced this event.       |
| `zone_start`           | string?   | Optional pitch zone at event start (e.g., `"defensive_third_left"`).       |
| `zone_end`             | string?   | Optional pitch zone at event end (for actions with clear destinations).    |
| `tags`                 | string?   | Semicolon-delimited tags (e.g., `"under_pressure;transition"`).            |
| `comment`              | string?   | Optional free-text comment.                                                |

`?` indicates an optional field.

---

## 3. First Touch Event

**`event_type = "first_touch"`**

Describes the **quality and immediate outcome of the first touch**.

### 3.1 Fields

| Field                    | Type    | Description                                                                 |
|--------------------------|---------|-----------------------------------------------------------------------------|
| `first_touch_quality`    | string  | `"high"`, `"medium"`, or `"low"`.                                           |
| `first_touch_result`     | string  | `"controlled"`, `"rebound_free_space"`, or `"rebound_opponent"`.           |
| `possession_after_touch` | string  | `"same_player"`, `"same_team_other_player"`, `"opponent"`, or `"loose"`.   |
| `maintained_possession_bool` | bool | `true` if same player/team keeps the ball; otherwise `false`.              |

### 3.2 Definitions

- **`first_touch_quality`**
  - `"high"` – Intentional trap and secure control; clearly deliberate and clean.
  - `"medium"` – Intentional trap, but control is shaky / bobbled; still likely possession.
  - `"low"` – Non-intentional, flailing, frantic, or indecisive; no real control.

- **`first_touch_result`**
  - `"controlled"` – Ball ends up clearly at the player’s feet in playing distance.
  - `"rebound_free_space"` – Ball squirts into neutral/unclaimed space.
  - `"rebound_opponent"` – An opponent clearly gains the ball after the touch.

- **`possession_after_touch`**
  - `"same_player"` – The same player ends up in possession after the touch.
  - `"same_team_other_player"` – A teammate takes possession directly after the touch.
  - `"opponent"` – Opponent team has clear possession after the touch.
  - `"loose"` – No team/player clearly controls the ball; 50/50 situation.

- **`maintained_possession_bool`**
  - `true` if `possession_after_touch ∈ {"same_player", "same_team_other_player"}`.
  - `false` otherwise.

---

## 4. On-Ball Action Event

**`event_type = "on_ball_action"`**

Describes **what the player does with the ball once they have it under control**.

### 4.1 Fields

| Field                    | Type    | Description                                                                 |
|--------------------------|---------|-----------------------------------------------------------------------------|
| `on_ball_action_type`    | string  | `"carry"`, `"pass"`, `"clearance"`, `"forward_ball"`, `"service"`, `"shot"`. |
| `touch_count_before_action` | string | `"one_touch"`, `"two_touch"`, `"three_plus"`.                               |
| `carry_flag`             | bool    | `true` if player carried/dribbled before the action; else `false`.         |
| `pass_intent`            | string? | `null` or intent for pass-like actions (see below).                        |
| `action_outcome_team`    | string  | `"same_team"`, `"opponent"`, `"out_of_play"`, `"loose"`.                   |
| `action_outcome_detail`  | string  | More granular outcome (see below).                                         |
| `next_possession_team`   | string  | `"same_team"`, `"opponent"`, `"contested"`.                                |

### 4.2 `on_ball_action_type`

- `"carry"` – Player moves/dribbles with the ball without immediate pass/shot/clearance.
- `"pass"` – Intentional ball to a teammate.
- `"clearance"` – Largely directionless or safety-first clearance to remove danger.
- `"forward_ball"` – Direct, often harder ball toward goal for a specific runner.
- `"service"` – Cross or service into attacking area (often from wide or attacking mids).
- `"shot"` – Attempt to score a goal.

### 4.3 `touch_count_before_action`

- `"one_touch"` – Action taken on the first touch.
- `"two_touch"` – Ball controlled, then action on second touch.
- `"three_plus"` – Action after three or more touches.

### 4.4 `carry_flag`

- `true` – Player visibly carried/dribbled the ball before the action (e.g., “carry then pass”).
- `false` – No meaningful carry prior to action (quick / stationary action).

### 4.5 `pass_intent` (for pass-like actions)

Used when `on_ball_action_type ∈ {"pass", "forward_ball", "service"}`.

- `null` – Not a pass-like action.
- `"safe_recycle"` – Conservative pass (often back/sideways) to retain possession.
- `"line_breaking"` – Pass that breaks at least one line of opponents.
- `"switch_of_play"` – Long lateral switch to opposite side.
- `"through_ball"` – Vertical ball into space for a runner behind or between defenders.
- `"service_into_box"` – Cross/service into the penalty area.
- `"other"` – Catch-all for any other intentional pattern not captured above.

### 4.6 `action_outcome_team`

- `"same_team"` – A teammate is in clear possession after the action.
- `"opponent"` – Opponent team in clear possession.
- `"out_of_play"` – Ball leaves the field of play.
- `"loose"` – 50/50 or scramble situation, no clear immediate owner.

### 4.7 `action_outcome_detail`

Granular outcome label:

- `"completed"` – Intended teammate controls the ball.
- `"intercepted"` – Opponent cuts the ball out before it reaches intended target.
- `"blocked"` – Action is blocked (e.g., cross blocked by defender).
- `"overhit"` – Too long/high; bypasses intended recipient or goes to GK/out.
- `"underhit"` – Too soft/short; fails to reach intended target.
- `"miscontrolled_by_teammate"` – Pass was acceptable; teammate’s touch causes loss.
- `"clearance_out"` – Clearance that directly goes out of play.
- `"shot_on_target"` – Shot would score without GK/defender intervention.
- `"shot_off_target"` – Shot misses the frame.
- `"shot_blocked"` – Shot blocked by defender before reaching goal.

### 4.8 `next_possession_team`

- `"same_team"` – Same team is in possession after all rebounds/contests settle.
- `"opponent"` – Opponent ends up in possession.
- `"contested"` – Ongoing duel/loose ball; no clear owner at the end of the observed moment.

---

## 5. Post-Loss Reaction Event

**`event_type = "post_loss_reaction"`**

Describes **the player’s behaviour immediately after losing possession**, and what comes of that behaviour.

### 5.1 Fields

| Field                      | Type    | Description                                              |
|----------------------------|---------|----------------------------------------------------------|
| `trigger_event_id`         | string  | `event_id` where possession was lost.                   |
| `post_loss_behaviour`      | string  | Behaviour label (see below).                            |
| `post_loss_effort_intensity` | string | `"high"`, `"medium"`, `"low"`.                          |
| `post_loss_outcome`        | string  | Outcome label (see below).                              |
| `post_loss_disruption_rating` | int? | Optional subjective rating (e.g., 1–5).                 |

### 5.2 `post_loss_behaviour`

- `"immediate_press"` – Quick, intentional attempt to pressure or win the ball.
- `"track_runner"` – Sprints to stay with attacker or cut passing lane.
- `"token_pressure"` – Light/jogging “pressure”; appears engaged but low intensity.
- `"no_reaction"` – Stands, walks, or watches; no meaningful attempt to re-engage.

### 5.3 `post_loss_effort_intensity`

- `"high"` – Full sprint or clearly committed effort.
- `"medium"` – Honest but not maximal effort.
- `"low"` – Minimal effort.

(In practice, this can be inferred from `post_loss_behaviour` if desired.)

### 5.4 `post_loss_outcome`

- `"won_back_possession_self"` – Player personally regains possession.
- `"won_back_possession_team"` – Teammate regains possession, aided by her actions.
- `"forced_error_only"` – Opponent makes a mistake under pressure, but no clean win.
- `"no_effect"` – Opponent plays as desired; player’s behaviour has negligible effect.
- `"negative_effect"` – Behaviour actively harms team (e.g., vacates key space, screens teammate, creates numerical disadvantage).

### 5.5 `post_loss_disruption_rating`

Optional integer scale (e.g., `1–5`) to capture how disruptive the player’s reaction was to the opponent’s ability to play forward.

---

## 6. Versioning Notes

- This document describes **Schema V1**.
- Any changes to field names, types, or semantics should:
  - Be captured in a new file (e.g., `Schema_V2.md`).
  - Increase the `Version` header.
  - Ideally be accompanied by migration notes (V1 → V2).
