from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from healthos_ai.api.schemas import ProviderPreference
from healthos_ai.config import Settings


class LLMGateway:
    """One provider-neutral gateway; LiteLLM owns credentials, routing, and fallback."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = AsyncOpenAI(
            base_url=str(settings.litellm_base_url),
            api_key=settings.litellm_master_key.get_secret_value(),
            timeout=settings.model_timeout_seconds,
            max_retries=1,
        )

    def chat(
        self, model: str, provider: ProviderPreference | str = ProviderPreference.AUTO
    ) -> ChatOpenAI:
        if provider != ProviderPreference.AUTO:
            provider_name = provider.value if isinstance(provider, ProviderPreference) else provider
            model = f"healthos-{provider_name}"
        return ChatOpenAI(
            model=model,
            base_url=str(self.settings.litellm_base_url),
            api_key=self.settings.litellm_master_key.get_secret_value(),
            timeout=self.settings.model_timeout_seconds,
            max_retries=1,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._client.embeddings.create(
            model=self.settings.embedding_model,
            input=texts,
            dimensions=self.settings.embedding_dimensions,
        )
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]

    async def healthy(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False
