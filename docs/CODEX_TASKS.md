# Codex Task Contract – Soccer Touch Analysis

This file defines how Codex should behave when working on this repository.

If there is any conflict between instructions, THIS FILE wins.

---

## Core Directives

1. Follow `docs/Functional_Requirements_V2.md` at all times.
2. Do NOT assume:
   - Real-time narration
   - Staccato keywords
   - Rigid spoken grammar
3. Parser implementations MUST be:
   - Chunk-based
   - LLM-driven
   - Schema-focused, not grammar-focused

---

## Allowed Work

Codex MAY:
- Implement LLM-based decomposition pipelines
- Add new endpoints for chunk processing
- Improve schema handling and validation
- Refactor code to support V2 workflows

---

## Disallowed Work

Codex MUST NOT:
- Reintroduce strict narration grammars
- Require users to speak faster or more precisely
- Optimize for human speed instead of human comfort

---

## Default Assumptions

- Narration is natural language
- Structure is inferred
- Approximate timing is acceptable
- Human cognitive load is the primary constraint

---

## When Unsure

If Codex is uncertain how to proceed:

1. Re-read `Functional_Requirements_V2.md`
2. Prefer solutions that reduce human effort
3. Ask for clarification rather than enforcing structure
