"""Migrations: empty database, round trip, classroom (create_all) database, original UniTask database, model drift."""

import os
import tempfile
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app import models  # noqa: F401
from app.database import Base
from app.migrate import alembic_config, upgrade_database

TEST_PG = os.getenv("TEST_POSTGRES_URL")  # e.g. postgresql+psycopg://postgres@localhost:5432/unitask_test


def fresh_engine(name: str):
    if TEST_PG:
        engine = create_engine(TEST_PG)
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
        return engine
    return create_engine(f"sqlite:///{Path(tempfile.mkdtemp(), name).as_posix()}")


def drift(engine) -> list:
    with engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": False}), Base.metadata)
    # SQLite reflects some server defaults/indexes differently; only table/column existence matters here.
    return [d for d in diffs if isinstance(d, tuple) and d[0] in {"add_table", "remove_table", "add_column", "remove_column"}]


def test_empty_database_upgrades_to_head_without_drift():
    engine = fresh_engine("empty.db")
    assert upgrade_database(engine) == "0002"
    assert drift(engine) == []


def test_downgrade_and_upgrade_round_trip():
    from alembic import command

    engine = fresh_engine("roundtrip.db")
    upgrade_database(engine)
    config = alembic_config(engine.url.render_as_string(hide_password=False))
    command.downgrade(config, "0001")
    assert "profiles" not in inspect(engine).get_table_names()
    assert upgrade_database(engine) == "0002"
    assert drift(engine) == []


def test_classroom_database_keeps_its_data():
    from alembic import command

    engine = fresh_engine("classroom.db")
    command.upgrade(alembic_config(engine.url.render_as_string(hide_password=False)), "0001")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, name, role, created_at) VALUES (1, 'a@x.edu', 'A', 'student', CURRENT_TIMESTAMP)"))
        conn.execute(text("DROP TABLE alembic_version"))  # as if it had been built by create_all
    assert upgrade_database(engine) == "0002"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT email FROM users")).scalar_one() == "a@x.edu"
    assert drift(engine) == []


@pytest.mark.skipif(bool(TEST_PG), reason="the original UniTask database was SQLite only")
def test_original_unitask_database_is_carried_forward():
    engine = fresh_engine("original.db")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE subjects (id INTEGER PRIMARY KEY, name VARCHAR(100), code VARCHAR(20), color VARCHAR(7), created_at DATETIME)"))
        conn.execute(text("CREATE TABLE assignments (id INTEGER PRIMARY KEY, title VARCHAR(200), subject_id INTEGER, due_date DATE, status VARCHAR(20), platform VARCHAR(100), description TEXT, created_at DATETIME, updated_at DATETIME)"))
        conn.execute(text("CREATE TABLE timetable_uploads (id VARCHAR(36) PRIMARY KEY, original_filename VARCHAR(255), object_key VARCHAR(512), storage_provider VARCHAR(20), content_type VARCHAR(100), size_bytes INTEGER, uploaded_at DATETIME)"))
        conn.execute(text("INSERT INTO subjects VALUES (1, 'Compiler Design', 'CS301', '#4f46e5', CURRENT_TIMESTAMP)"))
        conn.execute(text("INSERT INTO timetable_uploads VALUES ('u1', 'tt.png', 'timetables/u1.png', 's3', 'image/png', 10, CURRENT_TIMESTAMP)"))
    assert upgrade_database(engine) == "0002"
    tables = set(inspect(engine).get_table_names())
    assert {"subjects", "assignments", "users", "profiles"} <= tables and "legacy_timetable_uploads" not in tables
    with engine.connect() as conn:
        row = conn.execute(text("SELECT object_key, storage_provider, owner_id FROM timetable_uploads")).one()
    assert tuple(row) == ("timetables/u1.png", "s3", None)  # kept, unowned until claimed
