"""Onboarding: the level, skills and starter packs a user picks, and "I want this" clicks."""

from __future__ import annotations

from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_api.deps import current_user, get_db, require_csrf
from firstpr_platform.db import FeatureInterest, Profile, User, UserSkill, utcnow
from firstpr_platform.picks import SKILL_LEVELS, engine_settings
from issueradar.engine.rules import load_packs

router = APIRouter()

LEVELS = {
    "beginner": "New to open source. Small, well-described issues.",
    "intermediate": "I have opened a few pull requests before.",
    "pro": "I am comfortable finding my way in a big codebase.",
}
# Coming-soon features people can ask for. Counted on the admin page.
FEATURES = (
    "workspace",
    "vscode-extension",
    "ai-mentor",
    "leaderboard",
    "weekly-challenges",
    "learned-ranking",
    "career-paths",
    "teams",
)
MAX_SKILLS = 30

Kind = Literal["languages", "frameworks", "domains"]
SkillLevel = Literal["learning", "medium", "strong"]
Level = Literal["beginner", "intermediate", "pro"]


class Pack(BaseModel):
    key: str
    name: str
    description: str
    repos: list[str]


class Options(BaseModel):
    levels: dict[str, str]
    skill_levels: list[str]
    skills: dict[str, list[str]]
    packs: list[Pack]


class Skill(BaseModel):
    kind: Kind
    name: str
    level: SkillLevel


class ProfileOut(BaseModel):
    level: Level
    skills: list[Skill]
    packs: list[str]
    timezone: str
    onboarded: bool


class ProfileIn(BaseModel):
    level: Level = "beginner"
    skills: list[Skill] = Field(default_factory=list)
    packs: list[str] = Field(default_factory=list)
    timezone: str = "UTC"
    # True when the user finished (or skipped) onboarding with this save.
    finish: bool = True


class InterestIn(BaseModel):
    feature: str


def skill_options() -> dict[str, list[str]]:
    stack = engine_settings().stack
    return {
        "languages": sorted(set(stack.extensions.values())),
        "frameworks": sorted(stack.frameworks),
        "domains": sorted(stack.domains),
    }


@router.get("/onboarding/options", response_model=Options)
async def options() -> Options:
    return Options(
        levels=LEVELS,
        skill_levels=list(SKILL_LEVELS),
        skills=skill_options(),
        packs=[
            Pack(key=key, name=p.name, description=p.description, repos=list(p.repos))
            for key, p in load_packs().items()
        ],
    )


async def _read(db: AsyncSession, user: User) -> ProfileOut:
    profile = await db.get(Profile, user.id)
    rows = await db.scalars(
        select(UserSkill).where(UserSkill.user_id == user.id).order_by(UserSkill.id)
    )
    skills = [Skill(kind=r.kind, name=r.name, level=r.level) for r in rows]
    if profile is None:
        return ProfileOut(
            level="beginner", skills=skills, packs=[], timezone="UTC", onboarded=False
        )
    return ProfileOut(
        level=profile.level,
        skills=skills,
        packs=list(profile.packs or []),
        timezone=profile.timezone,
        onboarded=profile.onboarded_at is not None,
    )


@router.get("/me/profile", response_model=ProfileOut)
async def get_profile(
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> ProfileOut:
    return await _read(db, user)


@router.put("/me/profile", response_model=ProfileOut, dependencies=[Depends(require_csrf)])
async def save_profile(
    body: ProfileIn,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> ProfileOut:
    allowed = skill_options()
    seen: dict[tuple[str, str], Skill] = {}
    for skill in body.skills:
        name = skill.name.strip().lower()
        if name not in allowed[skill.kind]:
            raise HTTPException(422, f"Unknown {skill.kind[:-1]}: {skill.name}")
        seen[(skill.kind, name)] = Skill(kind=skill.kind, name=name, level=skill.level)
    if len(seen) > MAX_SKILLS:
        raise HTTPException(422, f"Pick at most {MAX_SKILLS} skills.")
    packs = load_packs()
    unknown = [p for p in body.packs if p not in packs]
    if unknown:
        raise HTTPException(422, f"Unknown starter pack: {unknown[0]}")
    try:
        ZoneInfo(body.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, "Unknown time zone") from None

    profile = await db.get(Profile, user.id)
    if profile is None:
        profile = Profile(user_id=user.id)
        db.add(profile)
    profile.level = body.level
    profile.packs = sorted(set(body.packs))
    profile.timezone = body.timezone
    if body.finish and profile.onboarded_at is None:
        profile.onboarded_at = utcnow()
    await db.execute(delete(UserSkill).where(UserSkill.user_id == user.id))
    db.add_all(
        UserSkill(user_id=user.id, kind=s.kind, name=s.name, level=s.level) for s in seen.values()
    )
    await db.commit()
    return await _read(db, user)


@router.get("/me/interest", response_model=list[str])
async def my_interest(
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[str]:
    rows = await db.scalars(
        select(FeatureInterest.feature).where(FeatureInterest.user_id == user.id)
    )
    return sorted(rows)


@router.post("/me/interest", response_model=list[str], dependencies=[Depends(require_csrf)])
async def want_feature(
    body: InterestIn,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[str]:
    if body.feature not in FEATURES:
        raise HTTPException(422, "Unknown feature")
    if await db.get(FeatureInterest, (user.id, body.feature)) is None:
        db.add(FeatureInterest(user_id=user.id, feature=body.feature))
        await db.commit()
    return await my_interest(user, db)
