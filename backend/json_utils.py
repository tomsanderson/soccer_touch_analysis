import json
from typing import Any, Dict, Optional, Tuple


def extract_json_object(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
    """
    Try to parse a JSON object from a string.
    Returns (json_obj, error_info).
    """
    if not text:
        return None, {"raw_text": "", "parse_error": "empty response"}

    cleaned = text.strip()
    cleaned = _strip_code_fence(cleaned)

    try:
        return json.loads(cleaned), None
    except Exception as exc:
        pass

    extracted = _extract_top_level_object(cleaned)
    if extracted:
        try:
            return json.loads(extracted), None
        except Exception as exc:
            return None, {"raw_text": text, "parse_error": str(exc)}

    return None, {"raw_text": text, "parse_error": "unable to locate JSON object"}


def _strip_code_fence(text: str) -> str:
    if text.startswith("```"):
        fence = "```json" if text.lower().startswith("```json") else "```"
        text = text[len(fence) :]
        if text.endswith("```"):
            text = text[: -3]
    return text.strip()


def _extract_top_level_object(text: str) -> Optional[str]:
    depth = 0
    start_idx: Optional[int] = None
    for idx, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start_idx = idx
            depth += 1
        elif char == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start_idx is not None:
                return text[start_idx : idx + 1]
    return None
