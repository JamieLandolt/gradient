"""Repository write paths that the API-level fakes can't exercise: they talk to the
real Supabase client chain, so these use a tiny in-memory stand-in for it."""

from typing import Any

import pytest
from postgrest.exceptions import APIError

from app.providers.interfaces import ExtractedProfile
from app.repositories.catalogue import CatalogueRepository
from app.repositories.ingestion import IngestionRepository


class _Result:
    def __init__(self, data: list[dict[str, Any]]):
        self.data = data


class _Query:
    def __init__(self, db: "FakeDb", table: str):
        self._db = db
        self._table = table
        self._op = "select"
        self._filters: list[tuple[str, Any]] = []
        self._payload: Any = None

    def select(self, _columns: str) -> "_Query":
        return self

    def eq(self, column: str, value: Any) -> "_Query":
        self._filters.append((column, value))
        return self

    def insert(self, payload: Any) -> "_Query":
        self._op = "insert"
        self._payload = payload
        return self

    def execute(self) -> _Result:
        rows = self._db.tables.setdefault(self._table, [])
        if self._op == "select":
            return _Result(
                [dict(r) for r in rows if all(r.get(k) == v for k, v in self._filters)]
            )
        payload = self._payload if isinstance(self._payload, list) else [self._payload]
        self._db.inserts.append((self._table, payload))
        hook = self._db.on_insert.get(self._table)
        if hook:
            hook(payload)  # may mutate tables and/or raise, like a concurrent writer
        stored = [{**row, "id": len(rows) + i + 1} for i, row in enumerate(payload)]
        rows.extend(stored)
        return _Result(stored)


class FakeDb:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.inserts: list[tuple[str, list[dict[str, Any]]]] = []
        self.on_insert: dict[str, Any] = {}

    def table(self, name: str) -> _Query:
        return _Query(self, name)


def _unique_violation() -> APIError:
    return APIError({"message": "duplicate key", "code": "23505", "hint": None, "details": None})


def _profile(**overrides: Any) -> ExtractedProfile:
    values: dict[str, Any] = dict(
        course_code="COMP2140", course_title="Web", units=2.0, description="d",
        version_label="2026S2", assessments=(), grade_cutoffs=None,
        prerequisite_raw=None, prerequisite_tree=None,
    )
    values.update(overrides)
    return ExtractedProfile(**values)


class TestSyncOfferings:
    def test_inserts_only_missing_pairs_in_one_call(self):
        db = FakeDb()
        db.tables["course_offerings"] = [{"course_id": 1, "year": 2025, "semester": "S1"}]

        created = CatalogueRepository(db).sync_offerings(
            1, [(2025, "S1"), (2025, "S2"), (2026, "S1"), (2026, "SUMMER")]
        )

        assert created == 3
        # One round-trip for all of them, not one per row.
        assert len(db.inserts) == 1
        assert {(r["year"], r["semester"]) for r in db.inserts[0][1]} == {
            (2025, "S2"), (2026, "S1"), (2026, "SUMMER"),
        }

    def test_is_idempotent(self):
        db = FakeDb()
        repo = CatalogueRepository(db)
        assert repo.sync_offerings(1, [(2025, "S1")]) == 1
        assert repo.sync_offerings(1, [(2025, "S1")]) == 0
        assert len(db.inserts) == 1

    def test_duplicate_input_pairs_are_inserted_once(self):
        db = FakeDb()
        assert CatalogueRepository(db).sync_offerings(1, [(2025, "S1"), (2025, "S1")]) == 1

    def test_never_deletes_offerings_missing_from_the_new_snapshot(self):
        db = FakeDb()
        db.tables["course_offerings"] = [{"course_id": 1, "year": 2009, "semester": "S1"}]
        CatalogueRepository(db).sync_offerings(1, [(2026, "S1")])
        assert {(r["year"], r["semester"]) for r in db.tables["course_offerings"]} == {
            (2009, "S1"), (2026, "S1"),
        }


class TestConcurrentDuplicateSubmissions:
    def test_losing_the_course_insert_race_reuses_the_winners_row(self):
        db = FakeDb()

        def winner_inserts_first(_payload):
            db.tables.setdefault("courses", []).append(
                {"id": 99, "code": "COMP2140", "title": "Web", "units": 2.0, "description": "d"}
            )
            raise _unique_violation()

        db.on_insert["courses"] = winner_inserts_first

        course, was_created = IngestionRepository(db).create_course_if_missing(_profile())

        assert course["id"] == 99
        # Not ours, so the caller must not attach prerequisites to it.
        assert was_created is False

    def test_other_course_insert_errors_still_propagate(self):
        db = FakeDb()

        def fails(_payload):
            raise APIError({"message": "boom", "code": "XX000", "hint": None, "details": None})

        db.on_insert["courses"] = fails

        with pytest.raises(APIError):
            IngestionRepository(db).create_course_if_missing(_profile())

    def test_losing_the_version_insert_race_returns_the_winner_and_adds_no_assessments(self):
        db = FakeDb()

        def winner_inserts_first(_payload):
            db.tables.setdefault("profile_versions", []).append(
                {"id": 7, "course_id": 1, "version_label": "2026S2", "status": "draft"}
            )
            raise _unique_violation()

        db.on_insert["profile_versions"] = winner_inserts_first

        version = IngestionRepository(db).create_draft_version(
            1, _profile(), source_type="text", source_ref="", provider_name="mock"
        )

        assert version["id"] == 7
        assert not any(table == "assessments" for table, _ in db.inserts)
