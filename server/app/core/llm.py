import os

from openai import AsyncOpenAI

from app.models.schemas import ModelConfigSummary


def resolve_temperature(value: float | None, default: float = 0.2) -> float:
    """Return the configured temperature, falling back only when unset.

    Explicit ``0.0`` must be preserved — a truthiness check would silently
    replace it with the default.
    """
    return default if value is None else value


class LLMClient:
    def __init__(self, config: ModelConfigSummary) -> None:
        api_key = os.getenv(config.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key environment variable: {config.api_key_env}")
        self.config = config
        self.client = AsyncOpenAI(api_key=api_key, base_url=config.base_url)

    async def complete(self, system: str, user: str) -> str:
        request_kwargs = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": resolve_temperature(self.config.temperature),
        }
        if self.config.max_tokens is not None:
            request_kwargs["max_tokens"] = self.config.max_tokens

        response = await self.client.chat.completions.create(**request_kwargs)
        return response.choices[0].message.content or ""
