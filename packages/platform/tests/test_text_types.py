"""Text from GitHub can hold NUL characters; PostgreSQL text columns cannot."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, select

from firstpr_platform.db import database_url
from issueradar.storage.types import SafeString, SafeText


def test_nul_characters_are_dropped_before_they_reach_the_database() -> None:
    assert SafeText().process_bind_param("a\x00b\x00", None) == "ab"
    assert SafeString(10).process_bind_param("x\x00y", None) == "xy"
    assert SafeText().process_bind_param(None, None) is None


@pytest.mark.skipif(
    not os.environ.get("FIRSTPR_TEST_DATABASE_URL"),
    reason="needs Postgres (CI sets FIRSTPR_TEST_DATABASE_URL)",
)
def test_postgres_takes_text_with_nul_characters() -> None:
    engine = create_engine(database_url(os.environ["FIRSTPR_TEST_DATABASE_URL"]))
    table = Table(
        "nul_text_check",
        MetaData(),
        Column("id", Integer, primary_key=True),
        Column("body", SafeText),
        Column("title", SafeString(50)),
        prefixes=["TEMPORARY"],
    )
    with engine.begin() as conn:
        table.create(conn)
        conn.execute(table.insert().values(id=1, body="one\x00two", title="t\x00"))
        assert conn.execute(select(table.c.body, table.c.title)).one() == ("onetwo", "t")
    engine.dispose()
