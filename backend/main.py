import csv
import io
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from openai import APIConnectionError, OpenAI, OpenAIError, RateLimitError

from .db import (
    get_upload,
    init_db,
    list_events_for_match,
    list_uploads,
    save_processing_result,
)
from .llm_parser import parse_transcript_segments

load_dotenv()

app = FastAPI(title="Soccer Touch Analysis Backend")

TRANSCRIPTION_MODEL_ENV = "TRANSCRIPTION_MODEL"
TRANSCRIPTS_DIR = Path("generated_transcripts")
EVENTS_DIR = Path("generated_events")


def get_transcription_model() -> str:
    model = os.getenv(TRANSCRIPTION_MODEL_ENV)
    if not model:
        raise RuntimeError(
            f"Environment variable {TRANSCRIPTION_MODEL_ENV} must be set to the transcription model name."
        )
    return model


client = OpenAI()
init_db()


@app.post("/upload-audio")
async def upload_audio(
    audio: UploadFile = File(...),
    match_id: str = Form(...),
    period: str = Form(...),
    team: Optional[str] = Form(None),
    narrator: Optional[str] = Form(None),
):
    if not audio.filename.lower().endswith(".m4a"):
        raise HTTPException(status_code=400, detail="Only .m4a audio files are supported.")

    if audio.content_type and not audio.content_type.startswith("audio"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an audio file.")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")

    transcription_model = get_transcription_model()

    audio_stream = io.BytesIO(audio_bytes)
    audio_stream.name = audio.filename

    try:
        transcript_response = client.audio.transcriptions.create(
            model=transcription_model,
            file=audio_stream,
            response_format="json",
        )
    except (RateLimitError, APIConnectionError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Transcription service temporarily unavailable. Please try again later.",
        ) from exc
    except OpenAIError as exc:
        status_code = getattr(exc, "status_code", 500) or 500
        detail = getattr(exc, "message", str(exc))
        raise HTTPException(
            status_code=status_code,
            detail=f"Transcription failed: {detail}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unexpected error during transcription.") from exc

    transcript_text = transcript_response.text
    segments = _extract_transcript_segments(transcript_response, transcript_text)
    events, parser_used = parse_transcript_segments(
        segments,
        match_id=match_id,
        period=period,
        offset_seconds=0.0,
        client=client,
    )
    timestamped_transcript = _format_timestamped_transcript(segments)
    csv_payload = _serialize_events_to_csv(events)
    csv_filename = _persist_csv_file(match_id, period, csv_payload)
    transcript_filename = _persist_transcript_file(
        match_id, period, timestamped_transcript
    )

    payload = {
        "match_id": match_id,
        "period": period,
        "team": team,
        "narrator": narrator,
        "transcript": transcript_text,
        "timestamped_transcript": timestamped_transcript,
        "events": events,
        "events_csv": csv_payload,
        "timestamped_transcript_file": transcript_filename,
        "timestamped_transcript_download_url": (
            f"/transcripts/{transcript_filename}" if transcript_filename else None
        ),
        "events_csv_file": csv_filename,
        "events_csv_download_url": f"/events/{csv_filename}" if csv_filename else None,
        "parser_used": parser_used,
    }

    save_processing_result(
        match_key=match_id,
        period=period,
        team=team,
        narrator=narrator,
        audio_filename=audio.filename,
        transcript_text=transcript_text,
        timestamped_transcript_text=timestamped_transcript,
        transcript_file_path=(
            str(TRANSCRIPTS_DIR / transcript_filename) if transcript_filename else None
        ),
        events_csv_path=str(EVENTS_DIR / csv_filename) if csv_filename else None,
        events=events,
    )

    return JSONResponse(content=payload)


@app.get("/uploads")
async def list_recent_uploads(limit: int = 50):
    limit = max(1, min(limit, 200))
    uploads = list_uploads(limit=limit)
    return JSONResponse(content={"uploads": uploads})


@app.get("/uploads/{upload_id}")
async def get_upload_details(upload_id: int):
    upload = get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found.")
    return JSONResponse(content=upload)


@app.get("/matches/{match_id}/events")
async def get_match_events(match_id: str, period: Optional[str] = None):
    events = list_events_for_match(match_key=match_id, period=period)
    return JSONResponse(content={"events": events})


CSV_FIELDS = [
    "event_id",
    "match_id",
    "period",
    "video_time_s",
    "team",
    "player_id",
    "player_name",
    "player_jersey_number",
    "player_role",
    "event_type",
    "possession_id",
    "sequence_id",
    "source_phrase",
    "zone_start",
    "zone_end",
    "tags",
    "comment",
    "first_touch_quality",
    "first_touch_result",
    "possession_after_touch",
    "maintained_possession_bool",
    "on_ball_action_type",
    "touch_count_before_action",
    "carry_flag",
    "pass_intent",
    "action_outcome_team",
    "action_outcome_detail",
    "next_possession_team",
    "trigger_event_id",
    "post_loss_behaviour",
    "post_loss_effort_intensity",
    "post_loss_outcome",
    "post_loss_disruption_rating",
]


def _extract_transcript_segments(
    transcript_response: Any, transcript_text: str
) -> List[Dict[str, Any]]:
    segments_obj = getattr(transcript_response, "segments", None)
    if segments_obj:
        return [
            {
                "start": float(_segment_value(seg, "start", 0.0)),
                "end": float(_segment_value(seg, "end", 0.0)),
                "text": str(_segment_value(seg, "text", "")),
            }
            for seg in segments_obj
            if str(_segment_value(seg, "text", "")).strip()
        ]

    fallback_segments: List[Dict[str, Any]] = []
    for idx, line in enumerate(transcript_text.splitlines()):
        text = line.strip()
        if not text:
            continue
        fallback_segments.append({"start": float(idx), "end": float(idx), "text": text})

    if fallback_segments:
        return fallback_segments

    if transcript_text.strip():
        return [{"start": 0.0, "end": 0.0, "text": transcript_text.strip()}]

    return []


def _segment_value(segment: Any, key: str, default: Any) -> Any:
    if isinstance(segment, dict):
        return segment.get(key, default)
    return getattr(segment, key, default)


def _serialize_events_to_csv(events: List[Dict[str, Any]]) -> str:
    if not events:
        return ""

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()

    for event in events:
        row = {field: event.get(field) for field in CSV_FIELDS}
        writer.writerow(row)

    return buffer.getvalue()


def _format_timestamped_transcript(segments: List[Dict[str, Any]]) -> str:
    if not segments:
        return ""

    lines: List[str] = []
    for segment in segments:
        start_seconds = float(segment.get("start", 0.0))
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        timestamp = _format_timestamp(start_seconds)
        lines.append(f"[{timestamp}] {text}")

    return "\n".join(lines)


def _format_timestamp(total_seconds: float) -> str:
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    centiseconds = int((total_seconds - int(total_seconds)) * 100)
    return f"{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def _persist_transcript_file(match_id: str, period: str, content: str) -> Optional[str]:
    if not content:
        return None

    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_match = _sanitize_for_filename(match_id)
    safe_period = _sanitize_for_filename(period)
    filename = f"{safe_match}_{safe_period}_{uuid4().hex}.txt"
    path = TRANSCRIPTS_DIR / filename
    path.write_text(content, encoding="utf-8")
    return filename


def _sanitize_for_filename(value: str) -> str:
    filtered = "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_"))
    return filtered or "match"


@app.get("/transcripts/{filename}")
async def download_transcript(filename: str):
    safe_filename = os.path.basename(filename)
    file_path = TRANSCRIPTS_DIR / safe_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Transcript file not found.")
    return FileResponse(
        file_path,
        media_type="text/plain",
        filename=safe_filename,
    )


def _persist_csv_file(match_id: str, period: str, content: str) -> Optional[str]:
    if not content:
        return None

    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_match = _sanitize_for_filename(match_id)
    safe_period = _sanitize_for_filename(period)
    filename = f"{safe_match}_{safe_period}_{uuid4().hex}.csv"
    path = EVENTS_DIR / filename
    path.write_text(content, encoding="utf-8")
    return filename


@app.get("/events/{filename}")
async def download_events_csv(filename: str):
    safe_filename = os.path.basename(filename)
    file_path = EVENTS_DIR / safe_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Events CSV not found.")
    return FileResponse(
        file_path,
        media_type="text/csv",
        filename=safe_filename,
    )


_FRONTEND_HTML = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Soccer Touch Analysis</title>
    <style>
      body {
        font-family: Arial, sans-serif;
        margin: 2rem;
        line-height: 1.4;
      }
      form {
        margin-bottom: 1.5rem;
        padding: 1rem;
        border: 1px solid #ccc;
        border-radius: 8px;
      }
      label {
        display: block;
        margin-top: 0.5rem;
      }
      input[type="text"],
      input[type="file"] {
        width: 100%;
        padding: 0.4rem;
        margin-top: 0.2rem;
      }
      button {
        margin-top: 1rem;
        padding: 0.5rem 1rem;
        font-size: 1rem;
      }
      pre {
        background: #f4f4f4;
        padding: 0.75rem;
        border-radius: 6px;
        overflow-x: auto;
      }
      .downloads a {
        margin-right: 1rem;
      }
      #status {
        margin-top: 0.5rem;
        font-style: italic;
      }
      #error {
        color: #b30000;
        margin-top: 0.5rem;
      }
    </style>
  </head>
  <body>
    <h1>Soccer Touch Analysis</h1>
    <p>Upload a narrated .m4a file to generate transcripts and structured events.</p>
    <form id="upload-form">
      <label>
        Match ID
        <input type="text" name="match_id" required />
      </label>
      <label>
        Period
        <input type="text" name="period" placeholder="e.g. 1 or 2" required />
      </label>
      <label>
        Team
        <input type="text" name="team" placeholder="Optional" />
      </label>
      <label>
        Narrator
        <input type="text" name="narrator" placeholder="Optional" />
      </label>
      <label>
        Audio (.m4a)
        <input type="file" name="audio" accept=".m4a,audio/m4a" required />
      </label>
      <button type="submit">Process Audio</button>
      <div id="status"></div>
      <div id="error"></div>
    </form>

    <section id="results" style="display:none;">
      <h2>Timestamped Transcript</h2>
      <pre id="timestamped-transcript"></pre>
      <div class="downloads" id="download-links"></div>
      <h2>Raw Transcript</h2>
      <pre id="raw-transcript"></pre>
      <h2>Events JSON</h2>
      <pre id="events-json"></pre>
    </section>

    <script>
      const form = document.getElementById("upload-form");
      const statusEl = document.getElementById("status");
      const errorEl = document.getElementById("error");
      const resultsSection = document.getElementById("results");
      const tsTranscriptEl = document.getElementById("timestamped-transcript");
      const rawTranscriptEl = document.getElementById("raw-transcript");
      const eventsJsonEl = document.getElementById("events-json");
      const downloadLinksEl = document.getElementById("download-links");

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        statusEl.textContent = "Processing audio…";
        errorEl.textContent = "";
        resultsSection.style.display = "none";

        const formData = new FormData(form);

        try {
          const response = await fetch("/upload-audio", {
            method: "POST",
            body: formData,
          });

          if (!response.ok) {
            const errorText = await response.text();
            throw new Error(errorText || "Upload failed.");
          }

          const result = await response.json();
          statusEl.textContent = "Processing complete.";
          resultsSection.style.display = "block";

          tsTranscriptEl.textContent = result.timestamped_transcript || "No transcript available.";
          rawTranscriptEl.textContent = result.transcript || "No transcript available.";
          eventsJsonEl.textContent = JSON.stringify(result.events, null, 2);

          downloadLinksEl.innerHTML = "";
          if (result.timestamped_transcript_download_url) {
            const link = document.createElement("a");
            link.href = result.timestamped_transcript_download_url;
            link.textContent = "Download timestamped transcript";
            link.target = "_blank";
            downloadLinksEl.appendChild(link);
          }
          if (result.events_csv_download_url) {
            const link = document.createElement("a");
            link.href = result.events_csv_download_url;
            link.textContent = "Download events CSV";
            link.target = "_blank";
            downloadLinksEl.appendChild(link);
          }
        } catch (err) {
          console.error(err);
          statusEl.textContent = "";
          errorEl.textContent = err.message || "Unexpected error.";
        }
      });
    </script>
  </body>
</html>
"""
@app.get("/")
async def index():
    return HTMLResponse(content=_FRONTEND_HTML)
