"""Local validation for the HealthMind meal-result contract."""

from __future__ import annotations

import json
import math
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

NutrientCode: TypeAlias = Literal[
    "ENERGY_KCAL",
    "PROTEIN",
    "FAT",
    "CARBOHYDRATE",
    "SUGAR",
    "DIETARY_FIBER",
    "SODIUM",
    "CALCIUM",
    "IRON",
    "POTASSIUM",
    "VITAMIN_C",
]
ReviewCode: TypeAlias = Literal[
    "IMAGE_UNAVAILABLE",
    "FOOD_UNRECOGNIZABLE",
    "WEIGHT_UNSUPPORTED",
    "EVIDENCE_CONFLICT",
    "CONTRACT_INVALID",
]


def _strict_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a JSON number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exception:
        raise ValueError("must be a finite JSON number") from exception
    if not math.isfinite(number):
        raise ValueError("must be finite")
    return number


class StrictResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Nutrient(StrictResultModel):
    code: NutrientCode
    value: float = Field(ge=0)

    @field_validator("value", mode="before")
    @classmethod
    def require_json_number(cls, value: object) -> float:
        return _strict_number(value)


class FoodItem(StrictResultModel):
    name: str = Field(min_length=1, max_length=150)
    weight_grams: float = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    nutrients: list[Nutrient] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def require_non_whitespace_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("weight_grams", "confidence", mode="before")
    @classmethod
    def require_json_numbers(cls, value: object) -> float:
        return _strict_number(value)

    @model_validator(mode="after")
    def reject_duplicate_nutrient_codes(self) -> FoodItem:
        codes = [nutrient.code for nutrient in self.nutrients]
        if len(codes) != len(set(codes)):
            raise ValueError("nutrient codes must be unique within an item")
        return self


class MealAnalysis(StrictResultModel):
    overall_confidence: float = Field(ge=0, le=1)
    items: list[FoodItem] = Field(min_length=1, max_length=100)

    @field_validator("overall_confidence", mode="before")
    @classmethod
    def require_json_number(cls, value: object) -> float:
        return _strict_number(value)


class NeedsReview(StrictResultModel):
    status: Literal["needs_review"]
    reason_code: ReviewCode
    message: str = Field(min_length=1, max_length=500)

    @field_validator("message")
    @classmethod
    def require_non_whitespace_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


MealResult: TypeAlias = Annotated[MealAnalysis | NeedsReview, Field(union_mode="left_to_right")]
_RESULT_ADAPTER = TypeAdapter(MealResult)


def parse_meal_result(text: str) -> MealAnalysis | NeedsReview:
    """Parse one strict JSON object; markdown and wrapper fields are rejected."""
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("The model result must be a JSON object")
    return _RESULT_ADAPTER.validate_python(value)


def result_dict(result: MealAnalysis | NeedsReview) -> dict[str, object]:
    return result.model_dump(mode="json")
