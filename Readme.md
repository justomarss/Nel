# Nel

Nel is a local-first persistent digital personality and personal companion for
Ömər. The current interface is a Windows development CLI. It is not a generic
assistant framework or the final product interface.

## Tested Environment

- Windows
- Python 3.14.5
- SQLite from Python's standard library
- NVIDIA NIM through its OpenAI-compatible API

Other operating systems and Python versions are not release-qualified.

## Installation

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\verify_environment.py
```

The dependency file pins the exact OpenAI client, Pydantic v2, and
python-dotenv versions used by the test suite.

## Configuration

Create `.env` locally with these required names. Never commit or print their
values:

```text
NVIDIA_API_KEY
NVIDIA_MODEL
NVIDIA_BASE_URL
```

Optional settings:

- `NVIDIA_TIMEOUT_SECONDS`: greater than zero and at most 300; default `45`.
- `ENABLE_BACKGROUND_THOUGHTS`: strict boolean; default `false`.
- `NEL_DATABASE_PATH`: existing schema-v4 database; default
  `memory/nel.sqlite3`.

Configuration is validated during guarded runtime construction, not import.
Missing or malformed provider settings produce a redacted startup error.

## Startup

```powershell
.\.venv\Scripts\python.exe main.py
```

Runtime requires an existing validated schema-v4 database and never creates or
migrates production persistence. Schema v4 contains exactly eight STRICT
tables, two immutable-core identity triggers, and one goal-state index.

## Commands

```text
/remember TEXT
/fact list
/fact set FACT_KEY --value "VALUE" --confirm
/fact history FACT_KEY
/fact retire FACT_KEY --confirm --reason "REASON"
/goal create --title "TITLE" --success "SUCCESS CONDITION"
/goal list
/goal pause GOAL_ID --version VERSION
/goal resume GOAL_ID --version VERSION
/goal complete GOAL_ID --version VERSION --accept-success
/goal cancel GOAL_ID --version VERSION
/goal reopen GOAL_ID --version VERSION --reason "REASON"
/goal restore GOAL_ID --version VERSION --reason "REASON"
/goal progress GOAL_ID --version VERSION --verification STATE [options]
```

Commands route through Decision Engine and their owning services without a
provider call. Ordinary conversation never writes raw memory. Provider-
proposed facts are temporary grounded candidates and require a confirmed
`/fact set` command before storage.

## Conversation Context

Every conversational provider request receives one canonical JSON data bundle
from `ContextAssembler`. Core identity is mandatory; relevant active facts,
goals, preferences, and memory events are selected deterministically. The data
bundle has a hard 12,000-character ceiling. No stored data is appended through
another prompt path.

## Tests

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test*.py'
.\.venv\Scripts\python.exe -m compileall -q main.py src scripts tests
git diff --check
```

Tests use temporary databases. They must not modify `memory/nel.sqlite3` or the
historical JSON snapshots.

## Backup

Stop Nel, create a destination directory under the ignored backup tree, then
use the existing backup service:

```powershell
$stamp = Get-Date -Format 'yyyyMMddTHHmmssZ'
$dir = "backups/sqlite-cutover/release/$stamp"
New-Item -ItemType Directory -Path $dir | Out-Null
$backup = "$dir/nel-schema-v4.sqlite3"
.\.venv\Scripts\python.exe -c "import sys; from src.persistence.backup import backup_sqlite_database; r=backup_sqlite_database(sys.argv[1],sys.argv[2]); print('PASS',r.validation_status,r.destination_path)" memory/nel.sqlite3 $backup
.\.venv\Scripts\python.exe -c "import sys; from src.persistence.backup import verify_sqlite_backup; print('PASS' if verify_sqlite_backup(sys.argv[1]) else 'FAIL')" $backup
```

Verification copies the backup to an isolated location, validates the complete
schema-v4 structure and integrity, and compares logical contents when the
backup is created. It never prints stored values.

## Restore

1. Stop Nel and create a fresh validated backup of the current database.
2. Copy the selected backup to `memory/nel.restore-candidate.sqlite3`.
3. Run `verify_sqlite_backup()` on the candidate before publication.
4. Move `memory/nel.sqlite3` to a timestamped `.pre-restore` file.
5. Move the verified candidate to `memory/nel.sqlite3`.
6. Start Nel and exit immediately, then confirm the database hash is unchanged.

Before the first post-restore write, rollback means restoring the preserved
pre-restore file. After new writes, never SQL down-migrate or pretend an older
snapshot is current; recovery requires an explicitly selected verified SQLite
backup and accepts its recovery-point loss.

`scripts/sqlite_cutover.py` is retired historical JSON-to-schema-v1 tooling.
Its CLI always refuses execution and is not a schema-v4 verifier.

## Known Limitations

- The current CLI is a development shell.
- NVIDIA requests may take up to the configured timeout.
- Context relevance is exact lexical matching and can miss paraphrases or
  Azerbaijani morphological variants.
- Background thoughts are disabled by default and have no write authority.
- Memory duplicate enforcement is lookup-based and can race under concurrent
  writers.
