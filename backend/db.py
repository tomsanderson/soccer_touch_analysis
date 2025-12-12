import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DB_PATH = Path(os.getenv("DATABASE_PATH", "data/app.db"))


def init_db() -> None:
    """Create the SQLite database and tables if they do not already exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_key TEXT NOT NULL,
                period TEXT NOT NULL,
                team TEXT,
                narrator TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(match_key, period)
            );

            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                audio_filename TEXT,
                transcript_text TEXT,
                timestamped_transcript_text TEXT,
                transcript_file_path TEXT,
                events_csv_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(match_id) REFERENCES matches(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                upload_id INTEGER NOT NULL,
                event_id TEXT,
                event_type TEXT,
                video_time_s REAL,
                team TEXT,
                player_id TEXT,
                player_name TEXT,
                player_jersey_number TEXT,
                player_role TEXT,
                possession_id TEXT,
                sequence_id TEXT,
                source_phrase TEXT,
                zone_start TEXT,
                zone_end TEXT,
                tags TEXT,
                comment TEXT,
                first_touch_quality TEXT,
                first_touch_result TEXT,
                possession_after_touch TEXT,
                maintained_possession_bool INTEGER,
                on_ball_action_type TEXT,
                touch_count_before_action TEXT,
                carry_flag INTEGER,
                pass_intent TEXT,
                action_outcome_team TEXT,
                action_outcome_detail TEXT,
                next_possession_team TEXT,
                trigger_event_id TEXT,
                post_loss_behaviour TEXT,
                post_loss_effort_intensity TEXT,
                post_loss_outcome TEXT,
                post_loss_disruption_rating TEXT,
                FOREIGN KEY(upload_id) REFERENCES uploads(id) ON DELETE CASCADE
            );
            """
        )


def save_processing_result(
    *,
    match_key: str,
    period: str,
    team: Optional[str],
    narrator: Optional[str],
    audio_filename: Optional[str],
    transcript_text: str,
    timestamped_transcript_text: str,
    transcript_file_path: Optional[str],
    events_csv_path: Optional[str],
    events: Sequence[Dict[str, Any]],
) -> None:
    """Persist the upload metadata and parsed events for later querying."""
    with _get_connection() as conn:
        match_id = _get_or_create_match(
            conn,
            match_key=match_key,
            period=period,
            team=team,
            narrator=narrator,
        )
        upload_id = conn.execute(
            """
            INSERT INTO uploads (
                match_id,
                audio_filename,
                transcript_text,
                timestamped_transcript_text,
                transcript_file_path,
                events_csv_path
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                match_id,
                audio_filename,
                transcript_text,
                timestamped_transcript_text,
                transcript_file_path,
                events_csv_path,
            ),
        ).lastrowid

        if events:
            rows = [_event_row(upload_id, event) for event in events]
            conn.executemany(
                """
                INSERT INTO events (
                    upload_id,
                    event_id,
                    event_type,
                    video_time_s,
                    team,
                    player_id,
                    player_name,
                    player_jersey_number,
                    player_role,
                    possession_id,
                    sequence_id,
                    source_phrase,
                    zone_start,
                    zone_end,
                    tags,
                    comment,
                    first_touch_quality,
                    first_touch_result,
                    possession_after_touch,
                    maintained_possession_bool,
                    on_ball_action_type,
                    touch_count_before_action,
                    carry_flag,
                    pass_intent,
                    action_outcome_team,
                    action_outcome_detail,
                    next_possession_team,
                    trigger_event_id,
                    post_loss_behaviour,
                    post_loss_effort_intensity,
                    post_loss_outcome,
                    post_loss_disruption_rating
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                rows,
            )

def list_uploads(limit: int = 50) -> List[Dict[str, Any]]:
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                uploads.id,
                matches.match_key,
                matches.period,
                matches.team,
                matches.narrator,
                uploads.audio_filename,
                uploads.transcript_file_path,
                uploads.events_csv_path,
                uploads.created_at,
                COUNT(events.id) as event_count
            FROM uploads
            JOIN matches ON uploads.match_id = matches.id
            LEFT JOIN events ON events.upload_id = uploads.id
            GROUP BY uploads.id
            ORDER BY uploads.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "id": row[0],
            "match_key": row[1],
            "period": row[2],
            "team": row[3],
            "narrator": row[4],
            "audio_filename": row[5],
            "transcript_file_path": row[6],
            "events_csv_path": row[7],
            "created_at": row[8],
            "event_count": row[9],
        }
        for row in rows
    ]


def get_upload(upload_id: int) -> Optional[Dict[str, Any]]:
    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                uploads.id,
                matches.match_key,
                matches.period,
                matches.team,
                matches.narrator,
                uploads.audio_filename,
                uploads.transcript_text,
                uploads.timestamped_transcript_text,
                uploads.transcript_file_path,
                uploads.events_csv_path,
                uploads.created_at
            FROM uploads
            JOIN matches ON uploads.match_id = matches.id
            WHERE uploads.id = ?
            """,
            (upload_id,),
        ).fetchone()
        if not row:
            return None

        events = conn.execute(
            """
            SELECT
                event_id,
                event_type,
                video_time_s,
                team,
                player_id,
                player_name,
                player_jersey_number,
                player_role,
                possession_id,
                sequence_id,
                source_phrase,
                zone_start,
                zone_end,
                tags,
                comment,
                first_touch_quality,
                first_touch_result,
                possession_after_touch,
                maintained_possession_bool,
                on_ball_action_type,
                touch_count_before_action,
                carry_flag,
                pass_intent,
                action_outcome_team,
                action_outcome_detail,
                next_possession_team,
                trigger_event_id,
                post_loss_behaviour,
                post_loss_effort_intensity,
                post_loss_outcome,
                post_loss_disruption_rating
            FROM events
            WHERE upload_id = ?
            ORDER BY id ASC
            """,
            (upload_id,),
        ).fetchall()

    return {
        "id": row[0],
        "match_key": row[1],
        "period": row[2],
        "team": row[3],
        "narrator": row[4],
        "audio_filename": row[5],
        "transcript_text": row[6],
        "timestamped_transcript_text": row[7],
        "transcript_file_path": row[8],
        "events_csv_path": row[9],
        "created_at": row[10],
        "events": [_event_from_row(event_row) for event_row in events],
    }


def list_events_for_match(match_key: str, period: Optional[str] = None) -> List[Dict[str, Any]]:
    query = """
        SELECT
            events.event_id,
            events.event_type,
            events.video_time_s,
            events.team,
            events.player_id,
            events.player_name,
            events.player_jersey_number,
            events.player_role,
            events.possession_id,
            events.sequence_id,
            events.source_phrase,
            events.zone_start,
            events.zone_end,
            events.tags,
            events.comment,
            events.first_touch_quality,
            events.first_touch_result,
            events.possession_after_touch,
            events.maintained_possession_bool,
            events.on_ball_action_type,
            events.touch_count_before_action,
            events.carry_flag,
            events.pass_intent,
            events.action_outcome_team,
            events.action_outcome_detail,
            events.next_possession_team,
            events.trigger_event_id,
            events.post_loss_behaviour,
            events.post_loss_effort_intensity,
            events.post_loss_outcome,
            events.post_loss_disruption_rating,
            matches.period,
            uploads.created_at
        FROM events
        JOIN uploads ON events.upload_id = uploads.id
        JOIN matches ON uploads.match_id = matches.id
        WHERE matches.match_key = ?
    """
    params: List[Any] = [match_key]
    if period:
        query += " AND matches.period = ?"
        params.append(period)
    query += " ORDER BY uploads.created_at ASC, events.id ASC"

    with _get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [
        {
            **_event_from_row(row[:31]),
            "period": row[31],
            "upload_created_at": row[32],
        }
        for row in rows
    ]



def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _get_or_create_match(
    conn: sqlite3.Connection,
    *,
    match_key: str,
    period: str,
    team: Optional[str],
    narrator: Optional[str],
) -> int:
    row = conn.execute(
        "SELECT id FROM matches WHERE match_key = ? AND period = ?",
        (match_key, period),
    ).fetchone()
    if row:
        return int(row[0])

    cursor = conn.execute(
        """
        INSERT INTO matches (match_key, period, team, narrator)
        VALUES (?, ?, ?, ?)
        """,
        (match_key, period, team, narrator),
    )
    return int(cursor.lastrowid)


def _event_row(upload_id: int, event: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        upload_id,
        event.get("event_id"),
        event.get("event_type"),
        event.get("video_time_s"),
        event.get("team"),
        event.get("player_id"),
        event.get("player_name"),
        event.get("player_jersey_number"),
        event.get("player_role"),
        event.get("possession_id"),
        event.get("sequence_id"),
        event.get("source_phrase"),
        event.get("zone_start"),
        event.get("zone_end"),
        event.get("tags"),
        event.get("comment"),
        event.get("first_touch_quality"),
        event.get("first_touch_result"),
        event.get("possession_after_touch"),
        _bool_to_int(event.get("maintained_possession_bool")),
        event.get("on_ball_action_type"),
        event.get("touch_count_before_action"),
        _bool_to_int(event.get("carry_flag")),
        event.get("pass_intent"),
        event.get("action_outcome_team"),
        event.get("action_outcome_detail"),
        event.get("next_possession_team"),
        event.get("trigger_event_id"),
        event.get("post_loss_behaviour"),
        event.get("post_loss_effort_intensity"),
        event.get("post_loss_outcome"),
        event.get("post_loss_disruption_rating"),
    )


def _event_from_row(row: Sequence[Any]) -> Dict[str, Any]:
    return {
        "event_id": row[0],
        "event_type": row[1],
        "video_time_s": row[2],
        "team": row[3],
        "player_id": row[4],
        "player_name": row[5],
        "player_jersey_number": row[6],
        "player_role": row[7],
        "possession_id": row[8],
        "sequence_id": row[9],
        "source_phrase": row[10],
        "zone_start": row[11],
        "zone_end": row[12],
        "tags": row[13],
        "comment": row[14],
        "first_touch_quality": row[15],
        "first_touch_result": row[16],
        "possession_after_touch": row[17],
        "maintained_possession_bool": _int_to_bool(row[18]),
        "on_ball_action_type": row[19],
        "touch_count_before_action": row[20],
        "carry_flag": _int_to_bool(row[21]),
        "pass_intent": row[22],
        "action_outcome_team": row[23],
        "action_outcome_detail": row[24],
        "next_possession_team": row[25],
        "trigger_event_id": row[26],
        "post_loss_behaviour": row[27],
        "post_loss_effort_intensity": row[28],
        "post_loss_outcome": row[29],
        "post_loss_disruption_rating": row[30],
    }


def _bool_to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return 1 if bool(value) else 0


def _int_to_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    return bool(value)


__all__ = [
    "init_db",
    "save_processing_result",
    "list_uploads",
    "get_upload",
    "list_events_for_match",
]
