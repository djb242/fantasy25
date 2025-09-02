# Repository Guidelines

## Project Structure & Module Organization
- Source scripts: root directory (e.g., `get_projections_2025.py`, `espn_scraper.py`, `convert_json_to_csv.py`).
- Data artifacts: CSV/JSON/JSONL files in root (e.g., `espn_projections_2025.json`, `sleeper_players_raw.jsonl`). Prefer creating a `data/` subfolder for new large outputs.
- Platform scripts: `download_espn_projections.ps1` for Windows PowerShell automation.

## Build, Test, and Development Commands
- Run scripts (Python 3.10+): `python .\get_projections_2025.py`, `python .\convert_json_to_csv.py`.
- PowerShell helper: `pwsh .\download_espn_projections.ps1` (or `powershell -File ...`).
- Quick smoke check: `python -c "import json,sys;print('OK')"` to verify Python env before running larger jobs.

## Coding Style & Naming Conventions
- Indentation: 4 spaces; line length target ~100–120 chars.
- Naming: snake_case for files, functions, and variables (e.g., `nflverse_actuals_2024_dump.py`).
- Imports: standard library first, then third‑party, then local; keep imports at top of files.
- I/O: prefer explicit file paths and clear suffixes (`*_raw.jsonl`, `*_flat.csv`, `*_weekly_ppr.csv`).

## Testing Guidelines
- No formal test suite yet; add focused script‑level checks.
- Recommended: small fixtures under `tests/fixtures/` (e.g., 3–5 line JSONL) and smoke invocations that validate schema/columns.
- Local run examples: `python .\sleeper_projections_dump.py` then verify row/column counts match expectations.

## Commit & Pull Request Guidelines
- Commits: concise imperative subject (≤72 chars) + context body. Group data‑only updates separately from code changes.
- Do not commit secrets or credentials. Avoid committing very large, transient files; prefer `data/` and update `.gitignore` if needed.
- PRs: include purpose, sample commands run, input/output file names, and a short before/after summary (e.g., “added `*_regular_flat.csv` with columns X, Y, Z”). Attach small sample outputs if helpful.

## Security & Configuration Tips
- Rate limits and external APIs may change; handle retries and timeouts conservatively.
- Keep file operations robust: check existence, write atomically to temp then move, and log row counts.
- If adding config, prefer `.env` with `python-dotenv` and never commit secrets.

