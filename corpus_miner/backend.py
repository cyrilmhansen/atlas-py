import json
import urllib.error
import urllib.request
from typing import Any, Callable


class BackendError(RuntimeError):
    pass


class Backend:
    name = "backend"

    def extract(self, prompt: str) -> str:
        raise NotImplementedError


class FakeBackend(Backend):
    name = "fake"

    def __init__(self, response: str | dict[str, Any] | Callable[[str], str | dict[str, Any]]):
        self.response = response

    def extract(self, prompt: str) -> str:
        value = self.response(prompt) if callable(self.response) else self.response
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


class OpenAICompatibleBackend(Backend):
    name = "openai-compatible"

    def __init__(self, base_url: str, model: str, api_key: str | None = None, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def extract(self, prompt: str) -> str:
        url = self.base_url + "/v1/chat/completions"
        body = json.dumps({
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise BackendError(f"OpenAI-compatible backend unavailable: {exc}") from exc
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendError("backend response lacks choices[0].message.content") from exc
        if not isinstance(content, str):
            raise BackendError("backend content is not text")
        return content
