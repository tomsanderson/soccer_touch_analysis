# Soccer Touch Analysis – Version 1

A small personal app to turn **spoken narration of soccer games** into a **structured event table** for analyzing a player’s touches, decisions, and post-loss reactions.

- Input: Voice recording (e.g., iPhone Voice Memos) of you narrating what happens in the game.
- Processing:
  1. Transcribe audio with the OpenAI Audio API.
  2. For the `/upload-audio` endpoint, run the **V1 strict pipeline** (segment-based parser + CSV + persistence). For `/chunks/decompose`, run the **V2 chunk pipeline** (natural-language narration chunk → LLM decomposition, no storage).
- Output: CSV/JSON with a **StatsBomb-inspired event schema**, focused on:
  - First-touch quality and outcome  
  - What the player does with the ball  
  - Whether they keep or lose possession  
  - How they react after losing possession  

This is **Version 1** of both the schema and the narration grammar. The goal is something that’s usable immediately and can evolve over time.

---

## 1. Goals

- Provide a **repeatable workflow** to analyze one player’s touches and decisions across matches.
- Use a **human-friendly spoken mini-language** that can be narrated in real time or on replay.
- Map narration into a **StatsBomb-style event structure** so future features (e.g., CV/tracking) can build on it.
- Keep the app lightweight: simple backend + minimal UI, CSV export first.

---

## 2. High-Level Architecture

**Planned V1 architecture:**

- **Backend** (Python, FastAPI)
  - `/upload-audio` (V1 strict mode) uploads an audio file, transcribes it, and runs the original strict parser (LLM + regex fallback) to emit CSV + persisted events.
  - `/chunks/decompose` (V2 chunk mode) accepts narration text + a video window and asks the V2 LLM parser to infer events from natural language (no rigid grammar, no persistence).
  - Returns:
    - CSV download containing all events.
    - Optionally JSON for UI.

- **Frontend** (very simple, optional in V1)
  - File upload form (audio file, match metadata).
  - “Process & Download CSV” button.
  - Future: Table view + video time linking.

- **Storage**
  - V1 can be stateless: process in memory and return CSV.
  - Optionally store:
    - Original audio
    - Transcript JSON
    - Events CSV

---

## Backend Quickstart

The FastAPI backend is located in `backend/` and provides the `/upload-audio` endpoint for sending narration audio and match metadata. It transcribes `.m4a` files using the OpenAI Audio API.

1) Install dependencies:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

2) Configure environment variables (see `.env.example`):

```bash
export OPENAI_API_KEY=your_api_key_here
export TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
export STRUCTURE_MODEL=gpt-4o-mini
```

3) Run the server:

```bash
uvicorn main:app --reload
```

4) Send a request (example using `curl`):

```bash
curl -X POST "http://localhost:8000/upload-audio" \
  -F "audio=@/path/to/file.m4a" \
  -F "match_id=match-123" \
  -F "period=1" \
  -F "team=Blue" \
  -F "narrator=Coach"
```

The response returns the raw transcript text and echoes the metadata you provided.

---

## Data Persistence

- Parsed data is stored in a lightweight SQLite database at `data/app.db` (configurable via `DATABASE_PATH`).
- Timestamped transcript `.txt` files and events `.csv` files live in `generated_transcripts/` and `generated_events/` for easy auditing.
- These directories are ignored by git so local runs stay clean but can be mounted/preserved when running in Docker.
- Read/write APIs:
  - `POST /upload-audio` – **V1 strict pipeline**: transcribe, parse segments, emit CSV, persist to SQLite, and return transcript + structured events.
  - `POST /chunks/decompose` – **V2 chunk pipeline**: send a narration chunk + time window to the LLM decomposer; returns structured events without touching storage.
  - `GET /uploads` – list recent uploads with metadata and download paths.
  - `GET /uploads/{id}` – fetch transcript, timestamped transcript, and event list for one upload.
  - `GET /matches/{match_id}/events?period=1` – pull every stored event for a specific match (and period, if supplied).

---

## LLM Parser

- The `/upload-audio` path (V1) still calls the V1 parser in `backend/llm_parser.py`. It expects relatively structured segments and falls back to the legacy grammar parser for reliability.
- The V2 chunk parser lives in `backend/chunk_parser.py` and accepts natural-language narration chunks (aligned to time windows) without any rigid grammar.
- Each event returned by the model includes the original source phrase plus the StatsBomb-style attributes (e.g., `first_touch_quality`, `action_outcome_detail`). The backend assigns IDs, timestamps, and persists the rows.
- If an API key or `STRUCTURE_MODEL` is missing—or the call fails—we automatically fall back to the deterministic grammar parser in `backend/parser.py`, ensuring unit tests and offline runs keep working.
- Example narration scripts live in `docs/test_scripts/` for repeatable round-trip tests.

## V1 Strict Mode vs V2 Chunk Mode

- **V1 strict mode (`POST /upload-audio`)**
  - Input: `.m4a` upload + form metadata.
  - Flow: Transcribe audio, process each transcript segment via the V1 LLM + regex fallback, emit CSV, persist transcript/events to SQLite.
  - Expectation: Works well when narration roughly follows the original structured grammar.

- **V2 chunk mode (`POST /chunks/decompose`)**
  - Input: JSON chunk containing match metadata, a narration window, and natural-language narration text.
  - Flow: Send the chunk to the V2 semantic decomposer (`backend/chunk_parser.py`), which infers events from conversational narration. Returns events only (no file writing / persistence).
  - Expectation: Designed for slow, reflective narration aligned to time windows (see `docs/Functional_Requirements_V2.md`).

---

## Docker

Build and run the API in an isolated container:

```bash
docker build -t soccer-touch-analysis .
docker run --env-file .env -p 8000:8000 soccer-touch-analysis
```

Bind-mount the `data/`, `generated_transcripts/`, and `generated_events/` directories if you want host-side persistence.

## Roadmap & Ideas

- Validate the full end-to-end workflow with real 10-minute narrations (Alpha 2 milestone).
- Explore adding ML-driven intent/entity extraction once we have a vetted corpus of transcripts to reduce strict grammar dependence.

## 3. Data Model – Version 1 Schema

Each **row = one event**.

There are three main event types in V1:

1. `first_touch`
2. `on_ball_action`
3. `post_loss_reaction`

### 3.1 Core Metadata (all events)

Common fields on every event row:

- `event_id` – unique ID per row (integer or UUID).
- `match_id` – identifier for the game (string).
- `period` – `"1"`, `"2"`, `"ET1"`, `"ET2"`, etc.
- `video_time_s` – seconds from start of period (float).
- `team` – e.g., `"Blue"` or `"White"`.
- `player_id` – internal player ID.
- `player_name` – human-readable name.
- `player_jersey_number` – jersey number (string or int).
- `player_role` – optional, e.g., `"CM"`, `"RB"`, `"LW"`.
- `event_type` – one of:
  - `"first_touch"`
  - `"on_ball_action"`
  - `"post_loss_reaction"`
- `possession_id` – ID for the possession this event belongs to (can be approximate in V1).
- `sequence_id` – ID for a sub-sequence within a possession (can equal `possession_id` in V1).
- `source_phrase` – the raw or cleaned transcript text used to create this event.

Optional / future fields:

- `zone_start` / `zone_end` – pitch zones (e.g., `"defensive_third_left"`).
- `tags` – semicolon-delimited labels (e.g., `"under_pressure;transition"`).
- `comment` – free text.

---

### 3.2 First Touch (event_type = "first_touch")

Describes the **quality and immediate outcome of the first touch**.

- `first_touch_quality`:
  - `"high"` – intentional trap and secure control.
  - `"medium"` – intentional trap but questionable control.
  - `"low"` – non-intentional / flailing / frantic; no real control.

- `first_touch_result`:
  - `"controlled"` – ball clearly at player’s feet.
  - `"rebound_free_space"` – ball squirts into neutral space.
  - `"rebound_opponent"` – opponent clearly gains the ball.

- `possession_after_touch`:
  - `"same_player"` – player has it next.
  - `"same_team_other_player"` – teammate gains it.
  - `"opponent"` – opponent gains it.
  - `"loose"` – nobody clearly controls it (50/50 ball).

- `maintained_possession_bool`:
  - `true` if `possession_after_touch` is `"same_player"` or `"same_team_other_player"`.
  - `false` otherwise.

---

### 3.3 On-Ball Action (event_type = "on_ball_action")

Describes **what the player does with the ball when they keep it**.

**Action type & touches**

- `on_ball_action_type`:
  - `"carry"` – dribble/move with the ball.
  - `"pass"` – intentional ball to teammate.
  - `"clearance"` – safety-first clearance, little/no specific target.
  - `"forward_ball"` – direct, harder ball toward goal for a runner.
  - `"service"` – ball into attacking area (cross, cutback, lofted service).
  - `"shot"` – attempt on goal.

- `touch_count_before_action`:
  - `"one_touch"`
  - `"two_touch"`
  - `"three_plus"`

- `carry_flag` (bool):
  - `true` if the player carries/dribbles before the action (“carry then pass/shot”).
  - `false` if essentially stationary or instant action.

**Intent / flavor (for pass-like actions)**

- `pass_intent`:
  - `null` – not a pass-like action.
  - `"safe_recycle"` – backward/sideways, low risk.
  - `"line_breaking"` – pass that breaks a line of opponents.
  - `"switch_of_play"` – long lateral switch.
  - `"through_ball"` – vertical ball into space for a runner.
  - `"service_into_box"` – cross/service into the penalty area.
  - `"other"` – catch-all.

**Outcome**

- `action_outcome_team`:
  - `"same_team"` – teammate has possession after the action.
  - `"opponent"`
  - `"out_of_play"` – ball goes out.
  - `"loose"` – 50/50 / scramble.

- `action_outcome_detail`:
  - `"completed"` – intended teammate controls the ball.
  - `"intercepted"` – opponent cuts it out.
  - `"blocked"` – e.g., cross blocked by defender.
  - `"overhit"` – too long, through everyone / to GK / out.
  - `"underhit"` – dies before reaching target.
  - `"miscontrolled_by_teammate"` – pass was okay, but teammate’s touch loses it.
  - `"clearance_out"` – clearance that goes out of play.
  - `"shot_on_target"`
  - `"shot_off_target"`
  - `"shot_blocked"`

- `next_possession_team`:
  - `"same_team"`
  - `"opponent"`
  - `"contested"`

---

### 3.4 Post-Loss Reaction (event_type = "post_loss_reaction")

Describes **what the player does immediately after losing possession**, and what comes of it.

- `trigger_event_id` – `event_id` of the event where possession was lost.

- `post_loss_behaviour`:
  - `"immediate_press"` – quick, intentional attempt to pressure / win the ball.
  - `"track_runner"` – sprints to stay with attacker or cut passing lane.
  - `"token_pressure"` – jogs nearby; looks engaged but low intensity.
  - `"no_reaction"` – stands, walks, or watches.

- `post_loss_effort_intensity`:
  - `"high"`
  - `"medium"`
  - `"low"`

- `post_loss_outcome`:
  - `"won_back_possession_self"` – player wins the ball back herself.
  - `"won_back_possession_team"` – teammate wins it, aided by her actions.
  - `"forced_error_only"` – opponent misplays or rushes under pressure, but no clean win.
  - `"no_effect"` – opponent plays as they wish.
  - `"negative_effect"` – reaction actively harms team structure (e.g., leaves a big gap, screens teammate, etc.).

- `post_loss_disruption_rating` (optional):
  - Numeric subjective rating, e.g., `1–5`.

---

## 4. Spoken Grammar – Narration Templates (V1)

The app relies on a constrained spoken grammar so the parser can reliably extract events.

The three main templates:

1. **First Touch**
2. **On-Ball Action**
3. **Post-Loss Reaction**

You speak these as **separate, short phrases** while watching the video (live or replay).

### 4.1 Template 1 – First Touch

**Pattern**

> `[team] [player] first touch [quality], [result].`

**Tokens**

- `[team]` – `Blue`, `White` (or any fixed pair, but be consistent).
- `[player]` – jersey number or name, e.g., `seven`, `ten`, `Tegan`.
- `[quality]` – `high`, `medium`, `low`.
- `[result]` – one of:
  - `controlled`
  - `rebound free space`
  - `rebound to opponent`

**Examples**

- `Blue seven first touch high, controlled.`
- `Blue seven first touch medium, rebound free space.`
- `Blue seven first touch low, rebound to opponent.`

**Defaults / mapping**

- `controlled` → `possession_after_touch = "same_player"`.
- `rebound free space` → `possession_after_touch = "loose"`.
- `rebound to opponent` → `possession_after_touch = "opponent"`.

---

### 4.2 Template 2 – On-Ball Action

Used **when possession is maintained** after first touch.

**Pattern**

> `[team] [player] [touch-count]-touch [action] [optional intent], [outcome phrase].`

**Tokens**

- `[touch-count]`:
  - `one` → `one_touch`
  - `two` → `two_touch`
  - `three-plus` → `three_plus`

- `[action]` → `on_ball_action_type`:
  - `pass`
  - `forward ball`
  - `service`
  - `clearance`
  - `shot`
  - (You can say “carry then pass/shot” to set `carry_flag = true`.)

- `[optional intent]` (optional):
  - `safe recycle`
  - `line breaking`
  - `switch of play`
  - `through ball`
  - `service into box`

- `[outcome phrase]` → outcome fields:
  - `completed to [teammate/role]`
  - `to opponent`
  - `out for [throw/goal kick/corner]`
  - `blocked`
  - For shots:
    - `on target`
    - `off target`
    - `blocked`

**Examples**

- `Blue seven two-touch pass, safe recycle to center back, completed.`
- `Blue seven one-touch through ball to Blue nine, intercepted by opponent.`
- `Blue four three-plus-touch clearance, pure clearance out for throw.`
- `Blue eleven one-touch service into box, completed to Blue nine.`
- `Blue seven one-touch shot from edge of box, on target, saved.`

---

### 4.3 Template 3 – Post-Loss Reaction

Used right after a moment where **your team loses possession** (either on first touch or on-ball action).

**Pattern**

> `After losing it, [team] [player] [behaviour phrase], [outcome phrase].`

**Behaviour phrases → post_loss_behaviour**

- `immediate press`
- `track runner`
- `token pressure`
- `stops and watches`
- `gives up` (treated the same as `stops and watches`)

**Outcome phrases → post_loss_outcome**

- `wins it back herself` → `won_back_possession_self`
- `wins it back for the team` → `won_back_possession_team`
- `forces error, but no win` → `forced_error_only`
- `no effect` → `no_effect`
- `negative effect` → `negative_effect`

**Examples**

- `After losing it, Blue seven immediate press, wins it back herself.`
- `After losing it, Blue seven track runner, wins it back for the team.`
- `After losing it, Blue seven token pressure, no effect.`
- `After losing it, Blue seven stops and watches, negative effect.`

---

## 5. Recording Workflow (iPhone Voice Memos + Veo)

A practical V1 workflow using only your iPhone and the Veo video:

1. **Prepare**
   - Load the Veo video on your laptop/tablet and rewind to the start of the half.
   - Put in AirPods (optional but convenient).
   - Open **Voice Memos** on iPhone and create a new recording.

2. **Start of half**
   - Tap **Record** in Voice Memos.
   - Immediately say:  
     `First half, zero minutes, Blue in yellow, White in black, kickoff.`
   - Hit **Play** on the video.
   - From now on, narrate using the templates in Section 4.

3. **Optional mid-half markers**
   - Around 10:00 and 20:00 of video time, say:
     - `Mark, ten minutes.`
     - `Mark, twenty minutes.`
   - These provide additional sync points if needed.

4. **End of half**
   - When the half ends, say:
     `End first half.`
   - Stop the Voice Memo.

5. **Second half**
   - Repeat with a new recording:
     - `Second half, zero minutes, …`

Even if you don’t start audio and video at the exact same millisecond, you can later compute an offset using the “zero minutes” or “Mark, ten minutes” calls.

---

## 6. Repo Structure (Suggested)

You can adjust this as you implement, but this is a good starting point:

```text
soccer-touch-analysis/
├─ backend/
│  ├─ main.py              # FastAPI app, upload endpoint, transcription call
│  ├─ parser.py            # Transcript → events logic (implements V1 grammar)
│  ├─ models.py            # Event dataclasses / Pydantic models
│  ├─ requirements.txt     # FastAPI, Uvicorn, OpenAI, etc.
│  ├─ config.py            # Environment variable handling
│  └─ tests/
│     └─ test_parser.py    # Unit tests for parsing functions
├─ frontend/               # Optional (simple HTML or small React app)
├─ docs/
│  ├─ Schema_V1.md         # This spec (copied/refined)
│  └─ Grammar_V1.md        # Spoken grammar cheat sheet
├─ .env.example            # OPENAI_API_KEY, TRANSCRIPTION_MODEL, etc.
└─ README.md               # This file
