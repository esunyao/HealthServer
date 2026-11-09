"""Freeze externally significant prompt and output schemas before restructuring."""

import hashlib
import json

from nutriathena_agent.meal.contract import MealAnalysis, NeedsReview
from nutriathena_agent.meal.prompt import build_system_prompt


def test_prompt_assembly_preserves_the_approved_skill_bundle():
    assert hashlib.sha256(build_system_prompt().encode()).hexdigest() == (
        "1213a064be9a244741cd43dbf279569fc676224090e6a83c4c1f4ad686380001"
    )


def test_success_result_schema_is_unchanged():
    schema = json.dumps(MealAnalysis.model_json_schema(), sort_keys=True)
    assert hashlib.sha256(schema.encode()).hexdigest() == (
        "2a856f2050540c1bd8b140073794c520eecc11d5b3936a27c5fee73081f1d9cf"
    )


def test_review_result_schema_is_unchanged():
    schema = json.dumps(NeedsReview.model_json_schema(), sort_keys=True)
    assert hashlib.sha256(schema.encode()).hexdigest() == (
        "8a4acd4266ac28b51c480c2b8dc4b7ffaff82501c329559c90212e0df782d1eb"
    )
