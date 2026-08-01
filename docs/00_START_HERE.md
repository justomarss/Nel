# Nel: Start Here

## Purpose

This directory is the authoritative onboarding source for Nel. Nel is a
persistent digital personality and personal autonomous agent being built
initially for Ömər.

Read these documents before making material product or code changes.

## Authority

The documents have the following authority, from highest to lowest:

1. [Constitution](01_CONSTITUTION.md)
2. Accepted records in [Decisions](07_DECISIONS.md)
3. [Rules for AI](08_RULES_FOR_AI.md)
4. Approved architecture direction in [Architecture](04_ARCHITECTURE.md)
5. [Project](03_PROJECT.md) scope and success criteria
6. [Current State](06_CURRENT_STATE.md) and [Roadmap](05_ROADMAP.md)

The Constitution, accepted decisions, and Rules for AI are normative.
Current State and Roadmap are descriptive and must be updated as the
repository changes. A lower-authority document cannot override a
higher-authority document.

## Reading Order

1. This file
2. [Constitution](01_CONSTITUTION.md)
3. [Team](02_TEAM.md)
4. [Project](03_PROJECT.md)
5. [Architecture](04_ARCHITECTURE.md)
6. [Decisions](07_DECISIONS.md)
7. [Current State](06_CURRENT_STATE.md)
8. [Roadmap](05_ROADMAP.md)
9. [Rules for AI](08_RULES_FOR_AI.md)

AI agents must read `08_RULES_FOR_AI.md` before changing the repository.

## Repository Entry Points

- Supported development entry point: root `main.py`
- Temporary interface: command-line development shell
- Temporary composition root: `src/core/nel.py`
- Tests: `tests/`
- Private runtime data: `memory/*.json`

## Local Setup

The current Windows development flow is:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Required environment variable names are:

- `NVIDIA_API_KEY`
- `NVIDIA_MODEL`
- `NVIDIA_BASE_URL`

Never print their values. Never commit `.env`.

Run the focused automated tests with:

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test*.py' -v
```

Tests must use temporary isolated data and must not modify real memory.

## Documentation Maintenance

- Update Current State after verified behavioral or structural changes.
- Update Roadmap when a capability starts, finishes, or changes dependency.
- Add an ADR when a material decision is accepted or superseded.
- Amend the Constitution only through the approval process it defines.
- Keep technical explanations understandable to a non-programmer.

## Earlier Documents

Files such as `00_Design_Philosophy.md`, `01_Internal_State.md`, and
`TODO.md` predate this onboarding set. They are historical inputs, not
normative specifications. Do not delete or silently rewrite them; reconcile
useful content through an explicit decision or documentation change.
