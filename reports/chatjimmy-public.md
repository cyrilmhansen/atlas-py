# ChatJimmy public backend experiment

## Result

The public anonymous inference path is:

`POST https://chatjimmy.ai/api/chat`

It accepts the public client's JSON shape with `messages`, `data`, and
`chatOptions`, and returns a plain text stream containing a `<|stats|>` JSON
sentinel. Public model discovery returns `llama3.1-8B` owned by Taalas Inc.

Standalone reproduction succeeded without an API key, private session material,
or access-control circumvention.

## Semantic gate

Six representative frozen Corpus Miner V4 cases were tested. All HTTP requests
returned 200, but 0/6 passed validation. Failures included malformed/non-JSON
responses, duplicate observation keys, and invalid claim references. The gate
was therefore classified unusable and the full regression/concurrency phases
were correctly not run.

## Role

Classification: **UNSUITABLE / INACCESSIBLE for Corpus Miner V4 and FAST_SCOUT
evaluation in this run**. The public endpoint is accessible and very fast, but
no Atlas role is justified without first solving the frozen output-contract
failure. No public output was promoted to durable knowledge.
