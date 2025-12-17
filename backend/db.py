import json
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
                parser_used TEXT,
                event_count INTEGER,
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
    parser_used: str,
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
                events_csv_path,
                parser_used,
                event_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match_id,
                audio_filename,
                transcript_text,
                timestamped_transcript_text,
                transcript_file_path,
                events_csv_path,
                parser_used,
                len(events),
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
                uploads.parser_used,
                uploads.event_count,
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
            "parser_used": row[9],
            "event_count": row[10],
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
                uploads.created_at,
                uploads.parser_used,
                uploads.event_count
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
        "parser_used": row[11],
        "event_count": row[12],
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


def list_v2_events_for_match(match_key: str, period: Optional[str] = None) -> List[Dict[str, Any]]:
    query = """
        SELECT
            v2.id,
            v2.chunk_id,
            v2.decomposition_id,
            v2.event_type,
            v2.team,
            v2.player_name,
            v2.player_jersey_number,
            v2.approximate_time_s,
            v2.source_phrase,
            v2.first_touch_quality,
            v2.first_touch_result,
            v2.on_ball_action_type,
            v2.touch_count_before_action,
            v2.pass_intent,
            v2.action_outcome_team,
            v2.action_outcome_detail,
            v2.post_loss_behaviour,
            v2.post_loss_outcome,
            v2.post_loss_effort_intensity,
            v2.extra_fields,
            v2.created_at,
            chunks.period,
            chunks.video_start_s,
            chunks.video_end_s,
            chunks.team_context,
            chunks.status,
            decompositions.parse_ok,
            decompositions.created_at AS decomposition_created_at
        FROM v2_events AS v2
        JOIN narration_chunks AS chunks ON v2.chunk_id = chunks.id
        JOIN chunk_decompositions AS decompositions ON v2.decomposition_id = decompositions.id
        WHERE chunks.match_id = ?
    """
    params: List[Any] = [match_key]
    if period is not None:
        query += " AND chunks.period = ?"
        params.append(str(period))
    query += """
        ORDER BY chunks.video_start_s ASC,
                 COALESCE(v2.approximate_time_s, chunks.video_start_s) ASC,
                 v2.id ASC
    """

    with _get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    events: List[Dict[str, Any]] = []
    for row in rows:
        extra_fields = json.loads(row[19]) if row[19] else None
        events.append(
            {
                "id": row[0],
                "chunk_id": row[1],
                "decomposition_id": row[2],
                "event_type": row[3],
                "team": row[4],
                "player_name": row[5],
                "player_jersey_number": row[6],
                "approximate_time_s": row[7],
                "source_phrase": row[8],
                "first_touch_quality": row[9],
                "first_touch_result": row[10],
                "on_ball_action_type": row[11],
                "touch_count_before_action": row[12],
                "pass_intent": row[13],
                "action_outcome_team": row[14],
                "action_outcome_detail": row[15],
                "post_loss_behaviour": row[16],
                "post_loss_outcome": row[17],
                "post_loss_effort_intensity": row[18],
                "extra_fields": extra_fields,
                "created_at": row[20],
                "period": row[21],
                "video_start_s": row[22],
                "video_end_s": row[23],
                "team_context": row[24],
                "chunk_status": row[25],
                "parse_ok": bool(row[26]),
                "decomposition_created_at": row[27],
            }
        )
    return events



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


def create_narration_chunk(
    *,
    match_id: str,
    period: str,
    video_start_s: float,
    video_end_s: float,
    transcript_text: str,
    team_context: Optional[str],
    status: str = "draft",
    chunk_index: Optional[int] = None,
    hash_value: Optional[str] = None,
) -> int:
    with _get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO narration_chunks (
                match_id,
                period,
                video_start_s,
                video_end_s,
                transcript_text,
                team_context,
                status,
                chunk_index,
                hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match_id,
                period,
                video_start_s,
                video_end_s,
                transcript_text,
                team_context,
                status,
                chunk_index,
                hash_value,
            ),
        )
        return int(cursor.lastrowid)


def update_narration_chunk_status(chunk_id: int, status: str) -> None:
    with _get_connection() as conn:
        conn.execute(
            """
            UPDATE narration_chunks
            SET status = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status, chunk_id),
        )


def insert_chunk_decomposition(
    *,
    chunk_id: int,
    schema_version: str,
    prompt_version: Optional[str],
    model: Optional[str],
    raw_llm_text: str,
    parsed_json: Optional[str],
    parse_ok: bool,
    error_json: Optional[str],
    latency_ms: Optional[int],
    cost_usd: Optional[float] = None,
) -> int:
    with _get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO chunk_decompositions (
                chunk_id,
                schema_version,
                prompt_version,
                model,
                raw_llm_text,
                parsed_json,
                parse_ok,
                error_json,
                latency_ms,
                cost_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id,
                schema_version,
                prompt_version,
                model,
                raw_llm_text,
                parsed_json,
                1 if parse_ok else 0,
                error_json,
                latency_ms,
                cost_usd,
            ),
        )
        return int(cursor.lastrowid)


def insert_v2_events(
    *,
    chunk_id: int,
    decomposition_id: int,
    events: Sequence[Dict[str, Any]],
) -> None:
    if not events:
        return

    known_fields = {
        "event_type",
        "team",
        "player_name",
        "player_jersey_number",
        "approximate_time_s",
        "source_phrase",
        "first_touch_quality",
        "first_touch_result",
        "on_ball_action_type",
        "touch_count_before_action",
        "pass_intent",
        "action_outcome_team",
        "action_outcome_detail",
        "post_loss_behaviour",
        "post_loss_outcome",
        "post_loss_effort_intensity",
        "extra_fields",
    }

    rows: List[Tuple[Any, ...]] = []
    for event in events:
        extras = dict(event.get("extra_fields") or {})
        for key, value in event.items():
            if key in known_fields or key == "extra_fields":
                continue
            if value is not None:
                extras.setdefault(key, value)
        extra_json = json.dumps(extras) if extras else None
        rows.append(
            (
                chunk_id,
                decomposition_id,
                event.get("event_type"),
                event.get("team"),
                event.get("player_name"),
                event.get("player_jersey_number"),
                event.get("approximate_time_s"),
                event.get("source_phrase"),
                event.get("first_touch_quality"),
                event.get("first_touch_result"),
                event.get("on_ball_action_type"),
                event.get("touch_count_before_action"),
                event.get("pass_intent"),
                event.get("action_outcome_team"),
                event.get("action_outcome_detail"),
                event.get("post_loss_behaviour"),
                event.get("post_loss_outcome"),
                event.get("post_loss_effort_intensity"),
                extra_json,
            )
        )

    with _get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO v2_events (
                chunk_id,
                decomposition_id,
                event_type,
                team,
                player_name,
                player_jersey_number,
                approximate_time_s,
                source_phrase,
                first_touch_quality,
                first_touch_result,
                on_ball_action_type,
                touch_count_before_action,
                pass_intent,
                action_outcome_team,
                action_outcome_detail,
                post_loss_behaviour,
                post_loss_outcome,
                post_loss_effort_intensity,
                extra_fields
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            rows,
        )


def get_chunk_with_latest_decomposition(chunk_id: int) -> Optional[Dict[str, Any]]:
    with _get_connection() as conn:
        chunk_row = conn.execute(
            """
            SELECT
                id,
                match_id,
                period,
                video_start_s,
                video_end_s,
                transcript_text,
                team_context,
                status,
                chunk_index,
                created_at,
                updated_at,
                hash
            FROM narration_chunks
            WHERE id = ?
            """,
            (chunk_id,),
        ).fetchone()

        if not chunk_row:
            return None

        chunk = {
            "id": chunk_row[0],
            "match_id": chunk_row[1],
            "period": chunk_row[2],
            "video_start_s": chunk_row[3],
            "video_end_s": chunk_row[4],
            "transcript_text": chunk_row[5],
            "team_context": chunk_row[6],
            "status": chunk_row[7],
            "chunk_index": chunk_row[8],
            "created_at": chunk_row[9],
            "updated_at": chunk_row[10],
            "hash": chunk_row[11],
        }

        decomposition_row = conn.execute(
            """
            SELECT
                id,
                schema_version,
                prompt_version,
                model,
                raw_llm_text,
                parsed_json,
                parse_ok,
                error_json,
                latency_ms,
                cost_usd,
                created_at
            FROM chunk_decompositions
            WHERE chunk_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (chunk_id,),
        ).fetchone()

        latest_decomposition: Optional[Dict[str, Any]] = None
        events: List[Dict[str, Any]] = []

        if decomposition_row:
            decomposition_id = decomposition_row[0]
            latest_decomposition = {
                "id": decomposition_id,
                "schema_version": decomposition_row[1],
                "prompt_version": decomposition_row[2],
                "model": decomposition_row[3],
                "raw_llm_text": decomposition_row[4],
                "parsed_json": json.loads(decomposition_row[5]) if decomposition_row[5] else None,
                "parse_ok": bool(decomposition_row[6]),
                "error_json": json.loads(decomposition_row[7]) if decomposition_row[7] else None,
                "latency_ms": decomposition_row[8],
                "cost_usd": decomposition_row[9],
                "created_at": decomposition_row[10],
            }

            event_rows = conn.execute(
                """
                SELECT
                    id,
                    event_type,
                    team,
                    player_name,
                    player_jersey_number,
                    approximate_time_s,
                    source_phrase,
                    first_touch_quality,
                    first_touch_result,
                    on_ball_action_type,
                    touch_count_before_action,
                    pass_intent,
                    action_outcome_team,
                    action_outcome_detail,
                    post_loss_behaviour,
                    post_loss_outcome,
                    post_loss_effort_intensity,
                    extra_fields,
                    created_at
                FROM v2_events
                WHERE chunk_id = ? AND decomposition_id = ?
                ORDER BY COALESCE(approximate_time_s, 0), id
                """,
                (chunk_id, decomposition_id),
            ).fetchall()

            events = [
                {
                    "id": row[0],
                    "event_type": row[1],
                    "team": row[2],
                    "player_name": row[3],
                    "player_jersey_number": row[4],
                    "approximate_time_s": row[5],
                    "source_phrase": row[6],
                    "first_touch_quality": row[7],
                    "first_touch_result": row[8],
                    "on_ball_action_type": row[9],
                    "touch_count_before_action": row[10],
                    "pass_intent": row[11],
                    "action_outcome_team": row[12],
                    "action_outcome_detail": row[13],
                    "post_loss_behaviour": row[14],
                    "post_loss_outcome": row[15],
                    "post_loss_effort_intensity": row[16],
                    "extra_fields": json.loads(row[17]) if row[17] else None,
                    "created_at": row[18],
                }
                for row in event_rows
            ]

        return {
            "chunk": chunk,
            "latest_decomposition": latest_decomposition,
            "events": events,
        }


def insert_sb_raw_file(
    *,
    source: str,
    file_type: str,
    external_id: Optional[str],
    schema_version: Optional[str],
    raw_json: Dict[str, Any],
) -> int:
    payload = json.dumps(raw_json)
    with _get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO sb_raw_files (
                source,
                file_type,
                external_id,
                schema_version,
                raw_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (source, file_type, external_id, schema_version, payload),
        )
        return int(cursor.lastrowid)


def upsert_sb_match(match_json: Dict[str, Any]) -> int:
    match_id = match_json.get("match_id")
    if match_id is None:
        raise ValueError("match_json must include match_id.")

    competition = match_json.get("competition", {}) or {}
    season = match_json.get("season", {}) or {}
    home_team = match_json.get("home_team", {}) or {}
    away_team = match_json.get("away_team", {}) or {}

    home_team_id = home_team.get("home_team_id") or home_team.get("id")
    away_team_id = away_team.get("away_team_id") or away_team.get("id")
    home_team_name = home_team.get("home_team_name") or home_team.get("name")
    away_team_name = away_team.get("away_team_name") or away_team.get("name")

    payload = json.dumps(match_json)

    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO sb_matches (
                match_id,
                competition_id,
                season_id,
                match_date,
                kick_off,
                home_team_id,
                home_team_name,
                away_team_id,
                away_team_name,
                match_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                competition_id=excluded.competition_id,
                season_id=excluded.season_id,
                match_date=excluded.match_date,
                kick_off=excluded.kick_off,
                home_team_id=excluded.home_team_id,
                home_team_name=excluded.home_team_name,
                away_team_id=excluded.away_team_id,
                away_team_name=excluded.away_team_name,
                match_json=excluded.match_json,
                ingested_at=datetime('now')
            """,
            (
                match_id,
                competition.get("competition_id") or competition.get("id"),
                season.get("season_id") or season.get("id"),
                match_json.get("match_date"),
                match_json.get("kick_off"),
                home_team_id,
                home_team_name,
                away_team_id,
                away_team_name,
                payload,
            ),
        )
    return int(match_id)


def replace_sb_events(match_id: int, events: Sequence[Dict[str, Any]]) -> None:
    with _get_connection() as conn:
        conn.execute("DELETE FROM sb_events WHERE match_id = ?", (match_id,))
        if not events:
            return

        rows: List[Tuple[Any, ...]] = []
        for event in events:
            event_id = event.get("id")
            if event_id is None:
                continue
            team = event.get("team") or {}
            player = event.get("player") or {}
            event_type = event.get("type") or {}
            play_pattern = event.get("play_pattern") or {}
            location = event.get("location") or []
            location_x = float(location[0]) if len(location) >= 1 else None
            location_y = float(location[1]) if len(location) >= 2 else None
            rows.append(
                (
                    match_id,
                    event_id,
                    event.get("index"),
                    event.get("period"),
                    event.get("timestamp"),
                    event.get("minute"),
                    event.get("second"),
                    team.get("id"),
                    team.get("name"),
                    player.get("id"),
                    player.get("name"),
                    event.get("possession"),
                    event_type.get("id"),
                    event_type.get("name"),
                    play_pattern.get("id"),
                    play_pattern.get("name"),
                    location_x,
                    location_y,
                    json.dumps(event),
                )
            )

        conn.executemany(
            """
            INSERT OR REPLACE INTO sb_events (
                match_id,
                event_id,
                index_in_match,
                period,
                timestamp,
                minute,
                second,
                team_id,
                team_name,
                player_id,
                player_name,
                possession,
                type_id,
                type_name,
                play_pattern_id,
                play_pattern_name,
                location_x,
                location_y,
                event_json
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            rows,
        )


__all__ = [
    "init_db",
    "save_processing_result",
    "list_uploads",
    "get_upload",
    "list_events_for_match",
    "list_v2_events_for_match",
    "create_narration_chunk",
    "update_narration_chunk_status",
    "insert_chunk_decomposition",
    "insert_v2_events",
    "get_chunk_with_latest_decomposition",
    "insert_sb_raw_file",
    "upsert_sb_match",
    "replace_sb_events",
]
