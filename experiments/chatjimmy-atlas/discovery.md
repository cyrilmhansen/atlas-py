# ChatJimmy backend discovery

## Actual endpoint

- endpoint tested: `http://192.168.1.188:8000`
- API shape: OpenAI-compatible `/v1/models` and `/v1/chat/completions`
- authentication: bearer key from the local oMLX/PI configuration; not copied into artifacts
- server identity exposed by the API: `uvicorn`, owner `omlx`
- machine observed from the client: x86-64 Linux, AMD Ryzen AI 9 HX 370

The endpoint exposed nine model identifiers. The experiment selected
`Qwen3.5-0.8B-OptiQ-4bit` as the high-throughput candidate. The larger exposed
models returned HTTP 409 while this model was loaded, so no claim is made about
their speed or quality here.

## API observations

The non-streaming probe returned the requested model, text content and usage.
The streaming probe accepted `stream_options.include_usage`, returned five SSE
chunks (one usage-only chunk), reconstructed `STREAM-OK`, and exposed:

- `prompt_tokens=18`
- `completion_tokens=3`
- `time_to_first_token=0.85`
- `total_time=0.85`

The backend accepted `chat_template_kwargs: {"enable_thinking": false}`.
No reasoning-content field was observed in the probe. These observations are
API facts only; they do not identify the server's internal scheduling policy.
