from datetime import datetime, timezone

from src.identity.models import IdentityRecord, IdentitySnapshot
from src.persistence.normalization import normalize_fact_key
from src.persistence.sqlite import SQLiteDatabase


CORE_KEYS = {"identity_id", "display_name", "nature", "role"}
PREFERENCE_PREFIX = "preference:"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _record(
    row,
    *,
    strip_preference_prefix=False,
    superseded_at=None,
) -> IdentityRecord:
    key = row["identity_key"]
    if strip_preference_prefix:
        key = key.removeprefix(PREFERENCE_PREFIX)
    return IdentityRecord(
        key=key,
        value=row["value"],
        record_type=row["record_type"],
        preference_state=row["preference_state"],
        immutable=bool(row["immutable"]),
        source_kind=row["source_kind"],
        source_reference=row["source_reference"],
        version=row["version"],
        updated_at=row["updated_at"],
        superseded_at=superseded_at,
    )


class IdentityRepository:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def snapshot(self) -> IdentitySnapshot:
        connection = self.database.connect()
        try:
            rows = connection.execute(
                """
                SELECT identity_key, record_type, value, preference_state,
                       immutable, source_kind, source_reference, version,
                       updated_at
                FROM nel_identity_current
                ORDER BY identity_key
                """
            ).fetchall()
        finally:
            connection.close()

        core = {
            row["identity_key"]: row["value"]
            for row in rows
            if row["record_type"] == "core"
        }
        if set(core) != CORE_KEYS:
            raise RuntimeError("Identity core is incomplete.")
        preferences = tuple(
            _record(row, strip_preference_prefix=True)
            for row in rows
            if row["record_type"] == "preference"
        )
        return IdentitySnapshot(
            identity_id=core["identity_id"],
            display_name=core["display_name"],
            nature=core["nature"],
            role=core["role"],
            preferences=preferences,
        )

    def get_preference(self, key: str) -> IdentityRecord | None:
        normalized = normalize_fact_key(key)
        connection = self.database.connect()
        try:
            row = connection.execute(
                """
                SELECT identity_key, record_type, value, preference_state,
                       immutable, source_kind, source_reference, version,
                       updated_at
                FROM nel_identity_current
                WHERE identity_key = ? AND record_type = 'preference'
                """,
                (PREFERENCE_PREFIX + normalized,),
            ).fetchone()
            return (
                None
                if row is None
                else _record(row, strip_preference_prefix=True)
            )
        finally:
            connection.close()

    def history(self, key: str) -> tuple[IdentityRecord, ...]:
        normalized = normalize_fact_key(key)
        connection = self.database.connect()
        try:
            rows = connection.execute(
                """
                SELECT identity_key, record_type, value, preference_state,
                       immutable, source_kind, source_reference, version,
                       valid_from AS updated_at, superseded_at
                FROM nel_identity_history
                WHERE identity_key = ?
                ORDER BY version
                """,
                (PREFERENCE_PREFIX + normalized,),
            ).fetchall()
            return tuple(
                _record(
                    row,
                    strip_preference_prefix=True,
                    superseded_at=row["superseded_at"],
                )
                for row in rows
            )
        finally:
            connection.close()

    def _create_candidate(
        self,
        key: str,
        value: str,
        source_kind: str,
        source_reference: str,
    ) -> IdentityRecord:
        identity_key = PREFERENCE_PREFIX + key
        now = _utc_now()
        with self.database.transaction() as connection:
            current = self._select_current(connection, identity_key)
            if current is None:
                connection.execute(
                    """
                    INSERT INTO nel_identity_current (
                        identity_key, record_type, value, preference_state,
                        immutable, source_kind, source_reference, version,
                        updated_at
                    ) VALUES (?, 'preference', ?, 'candidate', 0, ?, ?, 1, ?)
                    """,
                    (identity_key, value, source_kind, source_reference, now),
                )
            elif current["preference_state"] == "retired":
                self._replace_current(
                    connection,
                    current,
                    value=value,
                    state="candidate",
                    source_kind=source_kind,
                    source_reference=source_reference,
                    changed_at=now,
                )
            else:
                raise ValueError("An active preference already exists.")
        return self.get_preference(key)

    def _transition(
        self,
        key: str,
        expected_state: str,
        target_state: str,
        source_kind: str,
        source_reference: str,
    ) -> IdentityRecord:
        identity_key = PREFERENCE_PREFIX + key
        now = _utc_now()
        with self.database.transaction() as connection:
            current = self._select_current(connection, identity_key)
            if current is None:
                raise ValueError("Preference does not exist.")
            if current["preference_state"] != expected_state:
                raise ValueError("Preference state changed concurrently.")
            self._replace_current(
                connection,
                current,
                value=current["value"],
                state=target_state,
                source_kind=source_kind,
                source_reference=source_reference,
                changed_at=now,
            )
        return self.get_preference(key)

    @staticmethod
    def _select_current(connection, identity_key):
        return connection.execute(
            "SELECT * FROM nel_identity_current WHERE identity_key = ?",
            (identity_key,),
        ).fetchone()

    @staticmethod
    def _replace_current(
        connection,
        current,
        *,
        value,
        state,
        source_kind,
        source_reference,
        changed_at,
    ):
        if current["immutable"]:
            raise ValueError("Immutable identity records cannot change.")
        connection.execute(
            """
            INSERT INTO nel_identity_history (
                identity_key, record_type, value, preference_state,
                immutable, source_kind, source_reference, version,
                valid_from, superseded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                current["identity_key"],
                current["record_type"],
                current["value"],
                current["preference_state"],
                current["immutable"],
                current["source_kind"],
                current["source_reference"],
                current["version"],
                current["updated_at"],
                changed_at,
            ),
        )
        connection.execute(
            """
            UPDATE nel_identity_current
            SET value = ?, preference_state = ?, source_kind = ?,
                source_reference = ?, version = ?, updated_at = ?
            WHERE identity_key = ?
            """,
            (
                value,
                state,
                source_kind,
                source_reference,
                current["version"] + 1,
                changed_at,
                current["identity_key"],
            ),
        )
