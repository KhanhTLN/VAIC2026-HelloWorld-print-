from pydantic import BaseModel, ConfigDict, Field


class BrandCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class BrandUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class BrandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
