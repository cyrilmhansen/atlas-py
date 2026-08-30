# Atlas Codex release process

Atlas Agent uses a small, explicit patch set on top of the upstream OpenAI Codex CLI.

The goal is to keep the Atlas-specific delta small, auditable, and easy to reapply to each upstream Codex release.

## Branch model

Upstream releases are treated as immutable bases.

For each supported Codex release, create an Atlas release branch based exactly on the corresponding upstream tag:

```text
upstream tag:            rust-v0.152.0
Atlas release branch:    atlas/rust-v0.152.0
optional Atlas tag:      atlas-v0.152.0-1
```

`atlas/tool-allowlist` may continue to follow a newer upstream `main` for development and compatibility testing, but production Atlas Agent runtimes should preferably use an Atlas release branch based on an official upstream release.

## Atlas patch stack

Only Atlas-specific commits are reapplied to a new release.

Upstream commits that were temporarily cherry-picked into an older Atlas branch must not be carried forward if they are already part of the new upstream release.

For example:

```text
rust-v0.152.0
    |
    +-- Atlas: strict model tool allowlist
    +-- other Atlas-specific compatibility patches, if any
```

Keep the Atlas patch stack as small as possible.

## Updating to a new upstream release

Fetch upstream branches and tags:

```bash
git fetch upstream --tags
```

Create the new Atlas release branch directly from the upstream release tag:

```bash
git switch -c atlas/rust-v0.152.0 rust-v0.152.0
```

Cherry-pick the Atlas-specific commits:

```bash
git cherry-pick <atlas-tool-allowlist-commit>
```

Repeat only for other commits that are genuinely Atlas-specific.

If a cherry-pick conflicts, resolve the conflict against the new upstream implementation rather than mechanically preserving the old code. Changes to Codex tool registration, routing, hosted tools, Code Mode, or deferred tool discovery deserve particular attention because they may affect the Atlas allowlist security boundary.

## Verify the Atlas delta

The Atlas-specific differences should remain easy to inspect:

```bash
git diff rust-v0.152.0..atlas/rust-v0.152.0
```

Also inspect the commit stack:

```bash
git log --oneline rust-v0.152.0..atlas/rust-v0.152.0
```

The result should contain only intentional Atlas-specific changes.

## Development build

During porting and conflict resolution, use the development build for faster iteration:

```bash
cd codex-rs
cargo build -p codex-cli
```

The resulting executable is:

```text
codex-rs/target/debug/codex
```

Run targeted tests against this build while adapting the Atlas patches.

A development build is suitable for compatibility testing but should not become the production runtime pinned by Atlas Agent.

## Tests

Run the tests covering the Atlas tool registry and any upstream areas touched while resolving conflicts.

At minimum, validate the strict tool allowlist semantics:

* absent allowlist preserves the upstream tool surface;
* an explicit empty allowlist exposes no model tools;
* allowed tools remain available;
* disallowed registered tools are removed;
* hosted tools such as `web.run` are filtered;
* deferred/tool-search results cannot reveal disallowed tools;
* Code Mode cannot reintroduce disallowed tools;
* dispatch cannot invoke a tool excluded from the finalized registry.

Run broader Codex tests when upstream changes substantially overlap tool routing or configuration.

## Release build

Once the new Atlas release branch passes validation, build the production binary:

```bash
cargo build --release -p codex-cli
```

The production executable is:

```text
codex-rs/target/release/codex
```

Record its identity:

```bash
./target/release/codex --version
sha256sum ./target/release/codex
```

The version reported by the binary may reflect the upstream workspace release version. The authoritative Atlas runtime identity is the exact binary SHA-256 together with the upstream base and Atlas patch stack.

## Atlas Agent update

After rebuilding Codex, update Atlas Agent's pinned Codex binary SHA-256.

Do not reuse the SHA from the previous Atlas Codex build.

Then rerun the Atlas Agent test suite and runtime/profile validation before committing the new pin.

A runtime record should conceptually identify:

```text
upstream Codex release: rust-v0.152.0
Atlas release branch:   atlas/rust-v0.152.0
Atlas patches:          <commit list>
Codex binary SHA-256:   <sha256>
```

## Publishing the Atlas release branch

After validation:

```bash
git push origin atlas/rust-v0.152.0
```

An optional Atlas tag can identify a particular validated Atlas build:

```bash
git tag atlas-v0.152.0-1
git push origin atlas-v0.152.0-1
```

If another Atlas patch is required while remaining on the same upstream Codex release, increment the suffix:

```text
atlas-v0.152.0-1
atlas-v0.152.0-2
```

## Platform-specific binaries and reproducibility

The Atlas Codex source identity and the deployed binary identity are distinct.

A Git commit or Atlas Codex tag identifies the source tree and Atlas patch
stack. The SHA-256 pinned by Atlas Agent identifies the exact compiled binary.

Different target platforms therefore have different binary SHA-256 values even
when they are built from exactly the same source commit.

For example:

schema = "atlas-release/1"

atlas_agent_tag = "atlas-agent-v0.1.0"

[codex]
upstream_commit = "<upstream-commit>"
# upstream_tag = "rust-v0.152.0"  # only when this is the actual release base

atlas_tag = "atlas-v0.152.0-1"
atlas_commit = "<atlas-codex-commit>"

[[codex.binaries]]
target = "x86_64-unknown-linux-gnu"
sha256 = "<sha256>"

[[codex.binaries]]
target = "aarch64-unknown-linux-gnu"
sha256 = "<sha256>"

[[codex.binaries]]
target = "aarch64-apple-darwin"
sha256 = "<sha256>"

Do not assume that rebuilding the same source on the same architecture produces
a bit-for-bit identical binary unless reproducible-build properties have been
explicitly verified.

For every production build, record the SHA-256 of the actual binary that was
validated and deployed.

A release manifest may therefore contain several platform-specific binaries for
one Atlas Codex source release.

The manifest records the exact upstream and Atlas Codex commits.
`codex.upstream_tag` is optional and is recorded only when the Atlas patch stack
is actually based on that upstream release tag. The Atlas Agent commit itself is
resolved from `atlas_agent_tag` rather than embedded in the manifest.

## Updating the development branch

The development branch may separately be refreshed from `upstream/main` to detect future incompatibilities early.

It is not necessary for its history to match the release branches. The important invariant is that each production Atlas release branch has a clear upstream release base and a small, explicit Atlas patch stack.

## Guiding principle

Do not maintain a permanently merged fork when a small patch stack is sufficient.

Prefer:

```text
official upstream release
        +
small explicit Atlas patch stack
        =
validated Atlas Codex runtime
```

This keeps upgrades, audits, bisects, reproductions, and security reviews straightforward.
