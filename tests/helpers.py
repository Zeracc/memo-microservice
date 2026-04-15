from collections.abc import Iterator


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.expirations: dict[str, int | None] = {}
        self.set_calls: list[dict[str, object | None]] = []

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        self.expirations[key] = ex
        self.set_calls.append({"key": key, "value": value, "ex": ex})
        return True

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def ping(self) -> bool:
        return True

    def values_for_key(self, key: str) -> Iterator[dict[str, object | None]]:
        return (call for call in self.set_calls if call["key"] == key)
