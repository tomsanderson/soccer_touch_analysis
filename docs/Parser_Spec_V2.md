# Parser Spec – V2
LLM-Based Semantic Event Decomposition

This document defines how narration is converted into structured soccer events in V2.

V2 replaces strict grammar parsing with **LLM-driven semantic decomposition**.

---

## High-Level Architecture

### Inputs

For each narration unit (“chunk”):

- `transcript_text` (freeform natural language)
- `video_start_s`
- `video_end_s`
- Match context:
  - match_id
  - period
  - team colors / roster metadata

### Output

- Ordered list of atomic events
- Each event conforms to `Schema_V1` (or later Schema_V2)
- Each event includes:
  - event_type
  - player
  - team
  - inferred timestamp within window
  - inferred outcomes and qualities

---

## Core Responsibility Shift

| V1 | V2 |
|----|----|
| Human emits structured grammar | Human tells story |
| Parser extracts tokens | LLM infers structure |
| Regex-first | Semantics-first |

---

## Decomposition Process

For each narration chunk:

1. Provide the LLM with:
   - The narration text
   - The video time window
   - The event schema
2. Ask the LLM to:
   - Identify all soccer-relevant events described
   - Order them temporally
   - Map them to schema event types
3. For each inferred event:
   - Assign approximate timestamps within `[video_start_s, video_end_s]`
   - Populate schema fields probabilistically

---

## Example Prompt (Conceptual)

> “Given the following narration and time window, extract all atomic soccer events and return them as structured JSON objects following the schema.”

---

## Tolerance & Ambiguity

- Missing details are acceptable
- Fields may be null or inferred conservatively
- Precision is less important than **consistency and usability**

---

## Explicit Non-Goals

- Frame-accurate timing
- Perfect certainty
- Enforcing human narration discipline

---

## Parser Output Contract

- Output MUST be machine-readable JSON
- Output MUST preserve event order
- Output MUST be explainable (source_phrase retained)

---

## Versioning

This spec governs **Parser V2** behavior.

Any return to strict grammar or narration constraints violates Functional Requirements V2.
