"""Small interchangeable text-generation providers used by the RAG route."""

import os
from typing import Protocol


class LLMConfigurationError(RuntimeError):
    """Raised when the selected provider is not configured."""


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider cannot generate an answer."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMProvider(Protocol):
    def generate(self, system_instruction: str, user_prompt: str) -> str: ...


class CohereProvider:
    def __init__(self, api_key: str, model: str) -> None:
        import cohere

        self.client = cohere.ClientV2(api_key=api_key)
        self.provider = "cohere"
        self.model = model

    def generate(self, system_instruction: str, user_prompt: str) -> str:
        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = getattr(response.message, "content", [])
            for item in content:
                if getattr(item, "type", None) == "text" and getattr(item, "text", "").strip():
                    return item.text.strip()
            raise LLMProviderError("Cohere returned an empty answer")
        except LLMProviderError:
            raise
        except Exception as error:
            if _is_timeout(error):
                raise LLMProviderError("Cohere request timed out", status_code=504) from error
            raise LLMProviderError("Cohere could not generate an answer", status_code=_status_code(error)) from error


class GeminiProvider:
    def __init__(self, api_key: str, model: str) -> None:
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.provider = "gemini"
        self.model = model

    def generate(self, system_instruction: str, user_prompt: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config={"system_instruction": system_instruction},
            )
            answer = (getattr(response, "text", "") or "").strip()
            if not answer:
                raise LLMProviderError("Gemini returned an empty answer")
            return answer
        except LLMProviderError:
            raise
        except Exception as error:
            if _is_timeout(error):
                raise LLMProviderError("Gemini request timed out", status_code=504) from error
            raise LLMProviderError("Gemini could not generate an answer", status_code=_status_code(error)) from error


def _status_code(error: Exception) -> int | None:
    value = getattr(error, "status_code", None) or getattr(error, "code", None)
    return value if isinstance(value, int) else None


def _is_timeout(error: Exception) -> bool:
    return isinstance(error, TimeoutError) or "timeout" in error.__class__.__name__.lower()


def get_llm_provider() -> LLMProvider:
    provider = os.getenv("LLM_PROVIDER", "cohere").strip().lower()
    if provider == "cohere":
        api_key = os.getenv("COHERE_API_KEY", "").strip()
        if not api_key:
            raise LLMConfigurationError("COHERE_API_KEY is required when LLM_PROVIDER=cohere")
        return CohereProvider(api_key, os.getenv("COHERE_MODEL", "command-a-plus-05-2026"))
    if provider in {"gemini", "google", "google-gemini"}:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise LLMConfigurationError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
        return GeminiProvider(api_key, os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"))
    raise LLMConfigurationError(f"Unsupported LLM_PROVIDER: {provider}")
