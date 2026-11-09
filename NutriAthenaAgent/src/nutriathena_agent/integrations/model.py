"""Assemble configured model clients without owning configuration loading."""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from ..config import MealSettings


def build_model() -> ChatOpenAI:
    """Load teaching-model settings lazily when that command needs a model."""
    from ..config import load_model_settings

    settings = load_model_settings()
    return ChatOpenAI(
        model=settings.model,
        base_url=settings.base_url,
        api_key=settings.api_key,
    )


def build_meal_model(settings: MealSettings) -> ChatOpenAI:
    """Build the configured vision model with bounded retries and timeout."""
    return ChatOpenAI(
        model=settings.model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        temperature=0,
        timeout=180,
        max_retries=1,
    )
