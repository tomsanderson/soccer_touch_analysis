import io
import os
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from openai import APIConnectionError, OpenAI, OpenAIError, RateLimitError

app = FastAPI(title="Soccer Touch Analysis Backend")

TRANSCRIPTION_MODEL_ENV = "TRANSCRIPTION_MODEL"


def get_transcription_model() -> str:
    model = os.getenv(TRANSCRIPTION_MODEL_ENV)
    if not model:
        raise RuntimeError(
            f"Environment variable {TRANSCRIPTION_MODEL_ENV} must be set to the transcription model name."
        )
    return model


client = OpenAI()


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

    payload = {
        "match_id": match_id,
        "period": period,
        "team": team,
        "narrator": narrator,
        "transcript": transcript_text,
    }

    return JSONResponse(content=payload)
