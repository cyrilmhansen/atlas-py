# Atlas Agent v0.1.1 Codex assets

Install the contents of this directory into the dedicated Atlas `CODEX_HOME`.
The profile files use CODEX_HOME-relative paths, so prompt and catalog loading
does not depend on the target repository passed to `codex exec -C`.

The common base is `atlas-agent-prompts/common.md`. Implementation and review
instructions are selected by their profile. `state_audit.md` is selected by the
Atlas executor because the policy intentionally maps both read-only actions to
the same Sol profile.

The v0.1.0 files under `../v0.1.0/` are the exact imported canonical assets.
They remain unchanged for provenance; the v0.1.1 profile copies additionally
use relative catalog and prompt paths.
