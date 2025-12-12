# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) as it evolves.

## [Unreleased]

### Added
- SQLite persistence layer (matches, uploads, events) with API-generated transcripts/CSVs tracked on disk.
- Dockerfile/.dockerignore for containerized deployment.
- Read-only REST endpoints to list uploads, fetch upload details, and retrieve stored match events.
- LLM-driven parser (`STRUCTURE_MODEL`) with automatic fallback to the legacy grammar parser, plus documented prompt/example and narration test scripts.
- `uploads` table now records `parser_used` and `event_count` for auditing which parsing path handled each run.

## [v1.0.0] - 2025-12-12

### Added
- FastAPI backend with `/upload-audio` for `.m4a` narration uploads.
- OpenAI transcription integration with error handling.
- V1 parser converting transcript segments into structured events and CSV output.
- Automatic generation of timestamped transcript `.txt` files and downloadable CSV files.
- Minimal frontend upload form displaying transcripts, events preview, and download links.
- `.env` support via `python-dotenv`.

[Unreleased]: https://github.com/your-org/soccer_touch_analysis/compare/v1.0.0...HEAD
[v1.0.0]: https://github.com/your-org/soccer_touch_analysis/releases/tag/v1.0.0
