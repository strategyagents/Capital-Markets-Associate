"""Model selection utilities for Gemini and LiteLLM-backed deployments."""
from __future__ import annotations

import os
from dataclasses import dataclass

from .config import get_settings


@dataclass
class ModelConfig:
    provider: str
    identifier: str
    base_url: str | None = None


def resolve_model() -> ModelConfig:
    settings = get_settings()
    provider = settings.model_provider.lower()

    if provider == "litellm":
        if settings.litellm_base_url:
            os.environ.setdefault("LITELLM_BASE_URL", settings.litellm_base_url)
        if settings.litellm_api_key:
            os.environ.setdefault("LITELLM_API_KEY", settings.litellm_api_key)
        return ModelConfig(provider="litellm", identifier=settings.litellm_model, base_url=settings.litellm_base_url)

    if settings.google_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)
    return ModelConfig(provider="gemini", identifier=settings.default_google_model)
