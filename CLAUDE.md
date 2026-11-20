# Personal assistant (foundation of a conversational "butler" OS)

Purpose: build the foundational agent for a personal assistant that grows into the way people
interact with technology and with any company or entity, as a conversational butler acting on
the user's behalf (replacing the app-per-company smartphone model). Voice is an important
modality; AR glasses may add a visual layer later. Start small, build over time. See
`docs/decisions/0005-product-vision.md`.

Explain tradeoffs and write ADRs in `docs/decisions/`; longer design notes go in `docs/notes/`.

Design bias from the vision: the core stays modality- and device-agnostic (text, voice, AR are
adapters); the user's trust is the product, so anything that acts for the user is gated in code.

## Rules for this repo
- Python 3.14 in `.venv`. Run everything inside the venv. Install: `pip install -e ".[dev,labs]"`.
- Layering is enforced by `tests/test_layering.py`: `core/` must not import `adapters/` or
  `tools/`; only `adapters/` read the clock, environment, or `.env`.
- Every tool declares a risk level. Side-effecting tools (reversible/irreversible) must go
  through a code-enforced approval gate (Phase 3). Mock/sandbox only: no real credentials,
  no real money.
- Anything that must hold is enforced in code or hooks, never only in a prompt.
- Keep it simple: add agentic behavior only where the path cannot be predicted. State when
  the simpler option was chosen.
- Verify by running. Report failures honestly. Distinguish "tested offline" from "run live".
- Never write or print secrets. `.env` is git-ignored and is the user's to fill in.
- Check current Claude API / Agent SDK docs for model IDs and API details; do not rely on memory.

## Commands
- Tests (offline, no API key): `pytest`
- Lint/format: `ruff check . && ruff format .`
- Ask: `assistant ask "..." --trace`
- Live evals (spend money): `python evals/run_evals.py`
- Raw loop lab: `python labs/raw_loop.py "..."`
