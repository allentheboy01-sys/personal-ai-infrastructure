from typing import Type

from adapters.base import Adapter


class AdapterRegistry:
    def __init__(self):
        self._adapters: dict[str, Type[Adapter]] = {}

    def register(self, adapter_class: Type[Adapter]) -> None:
        provider_name = adapter_class.provider_name

        if not provider_name:
            raise ValueError("Adapter must define provider_name")

        if provider_name in self._adapters:
            raise ValueError(f"Adapter already registered: {provider_name}")

        self._adapters[provider_name] = adapter_class

    def get(self, provider_name: str) -> Type[Adapter]:
        if provider_name not in self._adapters:
            raise KeyError(f"No adapter registered for provider: {provider_name}")

        return self._adapters[provider_name]

    def list_providers(self) -> list[str]:
        return list(self._adapters.keys())