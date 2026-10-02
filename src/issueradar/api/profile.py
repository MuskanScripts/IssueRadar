"""The user's skill profile and saved views, stored in the database.

The CLI reads skills.yaml; the dashboard edits the same profile in the
database. When both exist, the database wins (it is the newer edit).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from issueradar.engine.stack import SkillProfile
from issueradar.storage.db import Database
from issueradar.storage.models import LOCAL_USER_ID, User
from issueradar.storage.models import SkillProfile as SkillRow

KINDS = ("languages", "frameworks", "domains")


def load(db: Database, user_id: int = LOCAL_USER_ID) -> SkillProfile | None:
    with db.sessions() as session:
        rows = list(session.scalars(select(SkillRow).where(SkillRow.user_id == user_id)))
        user = session.get(User, user_id)
        settings = dict(user.settings) if user else {}
    if not rows and "stretch" not in settings:
        return None
    data: dict[str, Any] = {kind: {} for kind in KINDS}
    for row in rows:
        data.setdefault(row.kind, {})[row.technology] = row.level
    data["stretch"] = bool(settings.get("stretch", False))
    data["prefer_issue_types"] = list(settings.get("prefer_issue_types", []))
    return SkillProfile.model_validate(data)


def save(db: Database, profile: SkillProfile, user_id: int = LOCAL_USER_ID) -> None:
    with db.sessions.begin() as session:
        session.execute(delete(SkillRow).where(SkillRow.user_id == user_id))
        for kind in KINDS:
            for tech, level in getattr(profile, kind).items():
                session.add(SkillRow(user_id=user_id, kind=kind, technology=tech, level=level))
        user = session.get_one(User, user_id)
        user.settings = {
            **user.settings,
            "stretch": profile.stretch,
            "prefer_issue_types": profile.prefer_issue_types,
        }


def views(db: Database, user_id: int = LOCAL_USER_ID) -> list[dict[str, Any]]:
    with db.sessions() as session:
        user = session.get(User, user_id)
        return list((user.settings if user else {}).get("views", []))


def save_views(db: Database, items: list[dict[str, Any]], user_id: int = LOCAL_USER_ID) -> None:
    with db.sessions.begin() as session:
        user = session.get_one(User, user_id)
        user.settings = {**user.settings, "views": items}
