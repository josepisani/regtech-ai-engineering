# Repo conventions

Keep this repo minimal. Rules to follow (including when using Claude Code here):

- **Only commit files necessary for THIS project.** No demo, example, or scratch
  files in the skeleton. If something is a one-off check, run it as a command —
  don't leave a file behind.
- **Secrets live only in `.env`** (git-ignored). Never commit keys; never print them.
- **Config comes from the environment** via `src/config.py` — don't hard-code settings.
- **Python env: uv.** `uv venv` + `uv pip install -r requirements.txt`.
- **Deploy target: Google Cloud Run** (`Dockerfile` + `webapp/`).
- Before committing, run `git status` and confirm `.env` is not staged and no
  scratch files snuck in.
