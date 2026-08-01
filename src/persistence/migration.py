import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path

from src.persistence.normalization import normalize_fact_key
from src.persistence.sqlite import SCHEMA_VERSION, SQLiteDatabase


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MigrationResult:
    memory_inserted: int
    memory_existing: int
    facts_inserted: int
    facts_existing: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as source:
            return json.load(source)
    except JSONDecodeError as exc:
        raise MigrationError(
            f"{path}: malformed JSON at line {exc.lineno}, "
            f"column {exc.colno}."
        ) from None
    except UnicodeError as exc:
        raise MigrationError(
            f"{path}: source is not valid UTF-8 ({type(exc).__name__})."
        ) from None
    except OSError as exc:
        raise MigrationError(
            f"{path}: source could not be read ({type(exc).__name__})."
        ) from None


def _validate_memory(path: Path, data) -> list[tuple[str, str]]:
    if not isinstance(data, list):
        raise MigrationError(f"{path}: expected a top-level list.")

    records = []
    for index, value in enumerate(data):
        if not isinstance(value, str):
            raise MigrationError(
                f"{path}: memory item at index {index} must be a string."
            )
        source_id = f"json:memory/long_term.json:{index}"
        records.append((source_id, value))
    return records


def _validate_knowledge(path: Path, data) -> list[tuple[str, str]]:
    if not isinstance(data, dict):
        raise MigrationError(f"{path}: expected a top-level object.")

    records = []
    normalized_keys = set()
    for key, value in data.items():
        if not isinstance(key, str):
            raise MigrationError(f"{path}: fact key must be a string.")
        if not isinstance(value, str):
            raise MigrationError(
                f"{path}: value for fact key {key!r} must be a string."
            )

        normalized_key = normalize_fact_key(key)
        if not normalized_key:
            raise MigrationError(
                f"{path}: fact key {key!r} is empty after normalization."
            )
        if normalized_key in normalized_keys:
            raise MigrationError(
                f"{path}: normalized-key collision for {normalized_key!r}."
            )

        normalized_keys.add(normalized_key)
        records.append((normalized_key, value))
    return records


def migrate_json_to_sqlite(
    database: SQLiteDatabase,
    long_term_path: str | Path,
    knowledge_path: str | Path,
    migrated_at: str | None = None,
) -> MigrationResult:
    long_term_path = Path(long_term_path)
    knowledge_path = Path(knowledge_path)

    memory_records = _validate_memory(
        long_term_path,
        _load_json(long_term_path),
    )
    fact_records = _validate_knowledge(
        knowledge_path,
        _load_json(knowledge_path),
    )

    try:
        version = database.current_schema_version()
    except sqlite3.DatabaseError as exc:
        raise MigrationError(
            f"SQLite target schema could not be read ({type(exc).__name__})."
        ) from None
    if version != SCHEMA_VERSION:
        raise MigrationError(
            f"SQLite target must use schema version {SCHEMA_VERSION}."
        )

    timestamp = migrated_at or _utc_now()
    memory_inserted = 0
    memory_existing = 0
    facts_inserted = 0
    facts_existing = 0
    context = "SQLite target"

    try:
        with database.transaction() as connection:
            for index, (source_id, value) in enumerate(memory_records):
                context = f"{long_term_path}: memory item at index {index}"
                existing = connection.execute(
                    "SELECT content FROM memory_events WHERE source_id = ?",
                    (source_id,),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO memory_events (
                            content, stored_at, source_id
                        ) VALUES (?, ?, ?)
                        """,
                        (value, timestamp, source_id),
                    )
                    memory_inserted += 1
                elif existing["content"] == value:
                    memory_existing += 1
                else:
                    raise MigrationError(
                        f"{context}: deterministic source ID conflict."
                    )

            for key, value in fact_records:
                context = f"{knowledge_path}: fact key {key!r}"
                existing = connection.execute(
                    """
                    SELECT value FROM user_facts_current
                    WHERE fact_key = ?
                    """,
                    (key,),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO user_facts_current (
                            fact_key, value, version, updated_at
                        ) VALUES (?, ?, 1, ?)
                        """,
                        (key, value, timestamp),
                    )
                    facts_inserted += 1
                elif existing["value"] == value:
                    facts_existing += 1
                else:
                    raise MigrationError(
                        f"{context}: conflicting current SQLite fact."
                    )
    except MigrationError:
        raise
    except sqlite3.DatabaseError as exc:
        raise MigrationError(
            f"{context}: database operation failed "
            f"({type(exc).__name__})."
        ) from None

    return MigrationResult(
        memory_inserted=memory_inserted,
        memory_existing=memory_existing,
        facts_inserted=facts_inserted,
        facts_existing=facts_existing,
    )
