"""
Pydantic request schemas for the routes most likely to receive malformed input.

Kept narrow on purpose — only validate at API boundaries that actually hurt
when they get garbage (LLM-facing endpoints, anything that branches on body
shape). Routes that take simple ints from the URL or no body at all don't
need a schema.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


SoloLevel = Literal["unistructural", "multistructural", "relational", "extended_abstract"]


class GenerateQuestionsRequest(BaseModel):
    """POST /api/generate-questions"""

    lesson_ids: List[int] = Field(min_length=1, description="One or more lesson IDs to draw from")
    solo_levels: List[SoloLevel] = Field(
        default_factory=lambda: ["unistructural", "multistructural", "relational"],
        min_length=1,
    )
    questions_per_level: int = Field(default=3, ge=1, le=20)
    section_ids: Optional[List[int]] = None
    save_to_db: bool = True

    @field_validator("lesson_ids")
    @classmethod
    def _dedupe_lesson_ids(cls, v: List[int]) -> List[int]:
        # Preserve order, drop dupes.
        seen = set()
        out = []
        for x in v:
            if x not in seen:
                out.append(x)
                seen.add(x)
        return out

    @field_validator("solo_levels")
    @classmethod
    def _dedupe_levels(cls, v: List[str]) -> List[str]:
        seen = set()
        out = []
        for x in v:
            if x not in seen:
                out.append(x)
                seen.add(x)
        return out
