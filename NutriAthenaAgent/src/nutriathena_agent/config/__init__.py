"""Configuration values and lazy environment loaders."""

from .models import (
    MealSettings,
    ModelSettings,
    RuntimeSettings,
    DEFAULT_MODEL,
    DEFAULT_MCP_SCOPES,
    MAX_MEAL_IMAGES,
    MAX_MEAL_IMAGE_BYTES,
    MAX_MEAL_TOTAL_IMAGE_BYTES,
    MAX_EVIDENCE_BYTES,
)
from .loader import (
    load_env,
    load_meal_settings,
    load_model_settings,
    load_runtime_settings,
    API_KEY_VAR,
    BASE_URL_VAR,
    MODEL_VAR,
    MEAL_MODEL_VAR,
)

__all__ = ['MealSettings', 'ModelSettings', 'RuntimeSettings', 'DEFAULT_MODEL', 'DEFAULT_MCP_SCOPES', 'MAX_MEAL_IMAGES', 'MAX_MEAL_IMAGE_BYTES', 'MAX_MEAL_TOTAL_IMAGE_BYTES', 'MAX_EVIDENCE_BYTES', 'load_env', 'load_meal_settings', 'load_model_settings', 'load_runtime_settings', 'API_KEY_VAR', 'BASE_URL_VAR', 'MODEL_VAR', 'MEAL_MODEL_VAR']
