"""Bring any UniTask database to the latest schema without losing data.

Handles three starting points:
- empty database               -> run every migration
- classroom build (create_all) -> stamp the baseline (0001), then upgrade
- original UniTask database    -> keep its subjects/assignments tables for the legacy import,
                                  carry its timetable uploads across, then upgrade
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)
BASELINE = "0001"


def alembic_config(url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


def upgrade_database(engine: Engine, revision: str = "head") -> str:
    config = alembic_config(engine.url.render_as_string(hide_password=False))
    tables = set(inspect(engine).get_table_names())
    legacy_timetables = False

    if "alembic_version" not in tables:
        if "users" in tables:
            from . import models  # noqa: F401 — registers every table on the metadata
            from .database import Base

            if set(Base.metadata.tables) <= tables:
                # Built by create_all at the current schema (tests, early dev databases).
                logger.info("Database already matches the current schema; stamping head.")
                command.stamp(config, "head")
            else:
                logger.info("Existing classroom database found; stamping baseline %s.", BASELINE)
                command.stamp(config, BASELINE)
        elif "timetable_uploads" in tables:
            logger.info("Original UniTask database found; keeping its data for the legacy import.")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE timetable_uploads RENAME TO legacy_timetable_uploads"))
            legacy_timetables = True

    command.upgrade(config, revision)

    if legacy_timetables:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO timetable_uploads (id, original_filename, object_key, storage_provider, content_type, "
                    "size_bytes, uploaded_at) SELECT id, original_filename, object_key, storage_provider, content_type, "
                    "size_bytes, uploaded_at FROM legacy_timetable_uploads"
                )
            )
            conn.execute(text("DROP TABLE legacy_timetable_uploads"))
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
