import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable


class BackendError(RuntimeError):
    pass


@dataclass
class StreamResult:
    content: str
    reasoning: str
    usage: dict[str, Any] = field(default_factory=dict)
    finish_reason: str | None = None


class Backend:
    name = "backend"

    def extract(self, prompt: str) -> str:
        raise NotImplementedError

    def extract_result(self, prompt: str) -> StreamResult:
        return StreamResult(self.extract(prompt), "")

    def extract_stream(self, prompt: str, on_reasoning: Callable[[str], None] | None = None,
                       on_content: Callable[[str], None] | None = None) -> StreamResult:
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

    def __init__(self, base_url: str, model: str, api_key: str | None = None, timeout: float = 60.0,
                 thinking: bool | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.thinking = thinking

    def extract(self, prompt: str) -> str:
        return self.extract_result(prompt).content

    def extract_result(self, prompt: str) -> StreamResult:
        request = self._request(prompt, stream=False)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise BackendError(f"OpenAI-compatible backend unavailable: {exc}") from exc
        try:
            choice = payload["choices"][0]
            message = choice["message"]
            content = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendError("backend response lacks choices[0].message.content") from exc
        if not isinstance(content, str):
            raise BackendError("backend content is not text")
        reasoning = message.get("reasoning_content", "")
        if not isinstance(reasoning, str):
            reasoning = ""
        return StreamResult(content=content, reasoning=reasoning, usage=payload.get("usage") or {},
                            finish_reason=choice.get("finish_reason"))

    def extract_stream(self, prompt: str, on_reasoning: Callable[[str], None] | None = None,
                       on_content: Callable[[str], None] | None = None) -> StreamResult:
        request = self._request(prompt, stream=True)
        reasoning_parts: list[str] = []
        content_parts: list[str] = []
        usage: dict[str, Any] = {}
        finish_reason = None
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
        except (OSError, urllib.error.URLError) as exc:
            raise BackendError(f"OpenAI-compatible backend unavailable: {exc}") from exc
        try:
            for raw_line in response:
                line = raw_line.decode("utf-8").rstrip("\r\n")
                if not line or not line.startswith("data:"):
                    continue
                payload_text = line[5:].strip()
                if payload_text == "[DONE]":
                    break
                try:
                    payload = json.loads(payload_text)
                except json.JSONDecodeError as exc:
                    raise BackendError(f"invalid SSE JSON data: {exc}") from exc
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("usage"), dict):
                    usage = payload["usage"]
                choices = payload.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                choice = choices[0]
                if not isinstance(choice, dict):
                    continue
                if choice.get("finish_reason") is not None:
                    finish_reason = choice["finish_reason"]
                delta = choice.get("delta")
                if not isinstance(delta, dict):
                    continue
                reasoning = delta.get("reasoning_content")
                if isinstance(reasoning, str) and reasoning:
                    reasoning_parts.append(reasoning)
                    if on_reasoning:
                        on_reasoning(reasoning)
                content = delta.get("content")
                if isinstance(content, str) and content:
                    content_parts.append(content)
                    if on_content:
                        on_content(content)
        finally:
            response.close()
        return StreamResult("".join(content_parts), "".join(reasoning_parts), usage, finish_reason)

    def _request(self, prompt: str, stream: bool) -> urllib.request.Request:
        url = self.base_url + "/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        if self.thinking is not None:
            payload["chat_template_kwargs"] = {"enable_thinking": self.thinking}
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        return urllib.request.Request(url, data=body, headers=headers, method="POST")
