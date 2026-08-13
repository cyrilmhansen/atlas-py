# ChatJimmy public backend observation

## PUBLIC PAGE

`https://chatjimmy.ai/` was inspected in the public web application. The page
loaded anonymously and presented the normal chat textbox; no login, API key,
CAPTCHA or user cookie was required for the observation and one minimal public
message.

## INFERENCE HOST

The public client uses same-origin relative paths on `chatjimmy.ai`:

- health: `GET /api/health`
- model discovery: `GET /api/models`
- inference: `POST /api/chat`

Static JavaScript inspection identified these paths in the public Next.js
chunks. The public `/api/models` response identified the service as:

```json
{"id":"llama3.1-8B","owned_by":"Taalas Inc."}
```

This is the public web backend, not `api.taalas.com`, the local oMLX server, or
any Atlas local endpoint.

## REQUEST SHAPE

The public client sends JSON with the following relevant shape:

```json
{
  "messages": [{"role": "user", "content": "..."}],
  "data": {},
  "chatOptions": {
    "selectedModel": "llama3.1-8B",
    "systemPrompt": "",
    "topK": 8
  }
}
```

An external request with this shape succeeded. A request containing only
`messages` returned HTTP 400, so `data` and `chatOptions` are part of the
observed public request contract rather than optional guesses.

## RESPONSE / STREAMING SHAPE

The response is HTTP 200 with `content-type: text/event-stream; charset=utf-8`
but the body is consumed by the public client as a plain text stream (`streamMode:
"text"`). The visible answer is followed by a stats sentinel:

```text
<|stats|>{...JSON...}<|/stats|>
```

Observed stats include `ttft`, `total_duration`, `prefill_rate`,
`decode_rate`, `total_tokens`, and `roundtrip_time`. A public browser probe
returned the visible response and showed roughly 0.002 seconds and 15,227
tokens/s in the UI; these figures are service-reported and not an independent
benchmark.

## AUTHENTICATION STATE

The public page and the successful minimal external request used no API key,
private session credential, CAPTCHA bypass, or protected token. Ordinary
`Content-Type: application/json` was sufficient for the external request.

## REPRODUCTION RESULT

The experiment-local `run_public_experiment.py` reproduces the request shape
and sends the frozen Corpus Miner V4 prompt unchanged. The standalone minimal
probe succeeded with the public endpoint.

The six-case semantic gate produced HTTP 200 for all six requests, but **0/6**
responses passed the existing V4 validator:

- duplicate observation key;
- response not raw JSON or one JSON-only fence;
- empty/non-JSON response after extraction;
- invalid `supported_by` references.

Because the small quality gate was clearly unusable, the full regression set
and public-service concurrency tests were not run.

## OBSERVED LIMITATIONS

- The public model identity is `llama3.1-8B`; no separate API model identifier
  was required by the web route.
- The public UI exposes a 6144-token context display and a `topK` control, but
  this observation does not establish all server limits.
- This experiment does not characterize `api.taalas.com` directly.
- The prior `192.168.1.188` experiment remains invalid for ChatJimmy backend
  identification and was not used here.
