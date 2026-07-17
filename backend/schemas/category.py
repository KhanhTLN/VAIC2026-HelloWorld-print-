from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    category_code: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)


class CategoryUpdate(BaseModel):
    category_code: str | None = Field(default=None, min_length=1, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=255)


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_code: str
    name: str
