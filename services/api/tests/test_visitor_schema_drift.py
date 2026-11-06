"""Schema drift guard: the Alembic-migrated schema must match the ORM models.

The regular API fixtures build tables with ``Base.metadata.create_all()``, which silently hides any
mismatch between the migrations (what production runs) and the models (what the code queries).
These tests upgrade a database through *every* migration and then compare table names, column
names, nullability and foreign-key targets for the Phase 6 visitor domain against the models.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.domains.visitors import models as visitor_models  # noqa: F401  (register mappers)

API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

VISITOR_TABLES = [
    "gates",
    "gate_assignments",
    "guest_passes",
    "visitors",
    "guest_pass_redemptions",
    "offline_sync_events",
    "guest_pass_failed_attempts",
]


def alembic_config() -> Config:
    cfg = Config(os.path.join(API_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(API_DIR, "migrations"))
    return cfg


@contextmanager
def migrated_engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    cfg = alembic_config()
    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
        connection.commit()
    try:
        yield engine
    finally:
        engine.dispose()


def _orm_columns(table_name: str) -> dict[str, bool]:
    table = Base.metadata.tables[table_name]
    return {c.name: bool(c.nullable) for c in table.columns}


def _orm_fk_targets(table_name: str) -> set[tuple[str, str]]:
    table = Base.metadata.tables[table_name]
    return {(fk.parent.name, fk.column.table.name) for fk in table.foreign_keys}


def _migrated_schema(
    engine: Engine, table_name: str
) -> tuple[dict[str, bool], set[tuple[str, str]]]:
    insp = inspect(engine)
    cols = {c["name"]: bool(c["nullable"]) for c in insp.get_columns(table_name)}
    fks: set[tuple[str, str]] = set()
    for fk in insp.get_foreign_keys(table_name):
        for col in fk["constrained_columns"]:
            fks.add((col, fk["referred_table"]))
    return cols, fks


@pytest.mark.parametrize("table_name", VISITOR_TABLES)
def test_migrated_schema_matches_orm_models(table_name: str) -> None:
    with migrated_engine() as engine:
        assert table_name in inspect(engine).get_table_names(), (
            f"Alembic head must create table '{table_name}' (ORM __tablename__)"
        )
        migrated_cols, migrated_fks = _migrated_schema(engine, table_name)

    orm_cols = _orm_columns(table_name)
    missing_in_migration = sorted(set(orm_cols) - set(migrated_cols))
    extra_in_migration = sorted(set(migrated_cols) - set(orm_cols))
    assert not missing_in_migration, f"{table_name}: ORM columns missing from migrations"
    assert not extra_in_migration, f"{table_name}: migrated columns unknown to the ORM"

    nullability_drift = {
        name: (orm_cols[name], migrated_cols[name])
        for name in orm_cols
        if orm_cols[name] != migrated_cols[name]
    }
    assert not nullability_drift, (
        f"{table_name}: nullability drift (orm, migrated) {nullability_drift}"
    )

    assert _orm_fk_targets(table_name) == migrated_fks, f"{table_name}: foreign-key drift"


def test_legacy_visitor_records_table_is_gone() -> None:
    with migrated_engine() as engine:
        assert "visitor_records" not in inspect(engine).get_table_names()


def test_migration_014_downgrade_and_reupgrade_round_trip() -> None:
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    cfg = alembic_config()
    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "013_gate_visitor_management")
        tables = inspect(connection).get_table_names()
        assert "visitor_records" in tables and "visitors" not in tables
        assert "guest_pass_failed_attempts" not in tables
        command.upgrade(cfg, "head")
        assert "visitors" in inspect(connection).get_table_names()
