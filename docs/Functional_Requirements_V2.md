# Functional Requirements – V2
Soccer Touch Analysis System

This document defines the **non-negotiable functional requirements** for Version 2 of the Soccer Touch Analysis system.

These requirements supersede any V1 assumptions about narration speed, grammar rigidity, or real-time capture.

---

## FR-1 — Natural Language Narration (Required)

- The system MUST accept **natural, conversational narration** as its primary human input.
- The user MUST NOT be required to:
  - Follow rigid sentence templates
  - Emit structured or tokenized phrases
  - Speak at the speed of live play
- Narration is expected to resemble:
  - Coach commentary
  - Post-play explanation
  - “Storytelling” of what happened

**Design implication:**  
Structure is inferred by the system, not imposed on the human.

---

## FR-2 — No Real-Time Narration Requirement (Required)

- The system MUST NOT assume narration occurs in real time.
- The workflow MUST support:
  - Pausing and rewinding video
  - Watching a sequence, then narrating after the fact
  - Describing multiple events from a short window of play
- Event timing is derived from:
  - Chunk-level time windows
  - Marker-based clip ranges
  - Approximate inference (not frame-accurate narration)

**Design implication:**  
Narration is aligned to **time windows**, not to live playback.

---

## FR-3 — Human Describes, System Structures (Required)

- The human’s role is to **describe what happened**.
- The system’s role is to:
  - Decompose narration into atomic events
  - Classify those events (first touch, on-ball action, post-loss reaction, etc.)
  - Populate the StatsBomb-inspired schema
  - Infer reasonable timestamps and outcomes

**Design implication:**  
Parser V2 is a **semantic event decomposer**, not a strict grammar parser.

---

## Explicitly Out of Scope for V2

The following are NOT allowed as required behaviors:

- Staccato keyword narration
- Token-based spoken grammars
- Real-time play-by-play narration
- Expecting the human to “keep up” with match speed

These approaches were tested and rejected due to excessive cognitive load.

---

## Success Criteria for V2

The system is considered successful if:

- A user can comfortably annotate a 1-minute clip in a **single pass**
- Narration feels calm, reflective, and natural
- The system consistently reconstructs structured events without narration strain
