"""Typed configuration entry points, loaded only when a command needs them."""

from .settings import (
    MealSettings, load_env, load_meal_settings, build_model, build_meal_model,
    DEFAULT_MODEL, DEFAULT_MCP_SCOPES, API_KEY_VAR, BASE_URL_VAR, MODEL_VAR, MEAL_MODEL_VAR,
    MAX_MEAL_IMAGES, MAX_MEAL_IMAGE_BYTES, MAX_MEAL_TOTAL_IMAGE_BYTES, MAX_EVIDENCE_BYTES,
)
from .runtime import RuntimeSettings, load_runtime_settings
