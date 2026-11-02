from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, field_validator

Text = Annotated[str, StringConstraints(strict=True, max_length=20_000)]
Identifier = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]


class ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceExcerpt(ContextModel):
    title: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    locator: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    text: Annotated[str, StringConstraints(min_length=1, max_length=16_000)]

    @field_validator("title", "locator", "text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Excerpt fields must contain text")
        return value


class ProjectContext(ContextModel):
    goal: Text = ""
    constraints: list[Annotated[str, StringConstraints(min_length=1, max_length=2000)]] = Field(
        default_factory=list, max_length=50
    )
    excerpts: list[SourceExcerpt] = Field(default_factory=list, max_length=20)

    @field_validator("constraints")
    @classmethod
    def nonblank(cls, values):
        if any(not value.strip() for value in values):
            raise ValueError("Constraints must contain text")
        return values


class BriefRequest(ContextModel):
    text: Annotated[str, StringConstraints(min_length=1, max_length=20_000)]
    name: Annotated[str, StringConstraints(min_length=1, max_length=120)] | None = None

    @field_validator("text", "name")
    @classmethod
    def nonblank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Supply nonblank text")
        return value


class ContextUpdate(ContextModel):
    context_revision: StrictInt = Field(ge=0)
    context: ProjectContext


class ProjectTarget(ContextModel):
    kind: Literal["project"]


class OccurrenceTarget(ContextModel):
    kind: Literal["occurrence"]
    occurrence_id: Identifier


class ChangeRequestCommand(ContextModel):
    request_id: Identifier
    context_revision: StrictInt = Field(ge=0)
    revision: StrictInt = Field(ge=1)
    target: Annotated[ProjectTarget | OccurrenceTarget, Field(discriminator="kind")]
    text: Annotated[str, StringConstraints(min_length=1, max_length=20_000)]

    @field_validator("text", "request_id")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Supply nonblank request text and ID")
        return value


class CapturedOccurrenceTarget(OccurrenceTarget):
    definition_id: Identifier
    affected_occurrence_ids: list[Identifier]


class CapturedRequest(ContextModel):
    id: Identifier
    created_at: str
    job_id: str
    text: str
    context_revision: StrictInt
    context: ProjectContext
    revision: StrictInt
    step_sha256: str | None = None
    target: Annotated[ProjectTarget | CapturedOccurrenceTarget, Field(discriminator="kind")]
    execution: Literal["pending"] = "pending"
    command: ChangeRequestCommand
