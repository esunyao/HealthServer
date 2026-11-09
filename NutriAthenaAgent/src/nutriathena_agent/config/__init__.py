"""Configuration values and lazy environment loaders."""
from .models import (
    MealSettings, ModelSettings, RuntimeSettings, DEFAULT_MODEL, DEFAULT_MCP_SCOPES,
    MAX_MEAL_IMAGES, MAX_MEAL_IMAGE_BYTES, MAX_MEAL_TOTAL_IMAGE_BYTES, MAX_EVIDENCE_BYTES,
)
from .loader import (
    load_env, load_meal_settings, load_model_settings, load_runtime_settings,
    API_KEY_VAR, BASE_URL_VAR, MODEL_VAR, MEAL_MODEL_VAR,
)

# Temporary migration adapters; removed when integrations.model is connected.
def build_model():
    from langchain_openai import ChatOpenAI
    settings = load_model_settings()
    return ChatOpenAI(model=settings.model, base_url=settings.base_url, api_key=settings.api_key)

def build_meal_model(settings):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=settings.model, base_url=settings.base_url, api_key=settings.api_key,
                      temperature=0, timeout=180, max_retries=1)
