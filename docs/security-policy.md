# Atlas Security Policy — Draft v0.2

This document is the current security-policy authority for Atlas Agent. It defines intended capability boundaries and threat-model scope. Existing implementation may contain documented gaps; adoption of this policy does not imply conformance.

## 1. Purpose

Atlas is primarily a local development and experimentation environment operated by a trusted user.

Atlas Agent executes AI-generated development actions and therefore requires explicit capability boundaries. Its security objective is to limit accidental, unintended, or instruction-induced effects of agent execution without turning Atlas into a hardened multi-user or hostile-host execution platform.

Security mechanisms SHOULD remain proportional to concrete threats and SHOULD NOT introduce substantial implementation, deployment, portability, or maintenance complexity without a documented threat that justifies them.

Security, reproducibility, workflow assurance, and development methodology are distinct concerns. They MAY share mechanisms, but MUST NOT be conflated.

## 2. Target security level

The default Atlas security profile is **Protected Local Development**.

It assumes:

* the operator is trusted;
* the operating system and user account are trusted;
* Atlas itself has been intentionally installed or adopted by the operator;
* ordinary local development tools are trusted to the same extent as they would be outside Atlas;
* project contents, generated text, web content, dependencies and model output may nevertheless contain incorrect, misleading or hostile instructions.

Atlas is not intended to provide a security boundary against a compromised host.

## 3. Assets protected

Atlas SHOULD primarily protect:

* files outside the authorized project workspace from unintended agent modification;
* repository metadata and workflow state from unauthorized mutation;
* credentials and private user data from unnecessary agent exposure;
* the user's network and external accounts from unintended agent actions;
* capability configuration from modification by untrusted task or repository content;
* the integrity and understandability of the development workflow.

Availability against a deliberately malicious local user or process is not a security objective.

Preserving correct contents inside files that an implementation agent is explicitly authorized to modify is primarily a correctness and durability concern rather than a capability-security property.

## 4. Explicit non-goals

Atlas does NOT attempt to defend against:

* root or kernel compromise;
* a malicious process already executing with the operator's Unix identity;
* deliberate tampering by the operator;
* physical compromise of the machine;
* a malicious Atlas installation deliberately accepted by the operator;
* complete isolation equivalent to a virtual machine or remote sandbox;
* arbitrary side-channel attacks;
* denial of service by an intentionally hostile local operator.

Security mechanisms MUST NOT be added solely to address these excluded threats unless Atlas explicitly introduces a separate hardened profile.

## 5. Authority model

Model output never constitutes authority.

Security authority comes from controller-owned policy established or adopted by the operator.

Individual executions MAY be selected, scheduled, parameterized or chained automatically within that pre-authorized capability envelope. Atlas does not require human approval for every execution.

Task content, prompts, repository files, AGENTS.md files, documentation, generated files, web pages, dependency metadata, model catalogues, automated planners and other agent-readable content MAY request or influence the use of capabilities but MUST NOT enlarge the authorized capability ceiling.

An agent MUST NOT be able to enlarge its own execution authority.

Capability restrictions MUST be enforced outside model-controlled natural-language instructions and before the requested action is executed.

Ambiguity concerning an actual authority boundary SHOULD fail closed.

## 6. Capability ceiling and execution grants

Atlas SHOULD distinguish:

* the **capability ceiling**: the maximum authority pre-authorized for a project, workflow or deployment;
* the **requested capabilities**: the authority requested by a particular task or automated decision;
* the **effective execution grant**: the actual capabilities supplied to that execution.

The effective execution grant MUST NOT exceed the capability ceiling.

Conceptually:

`effective grant ⊆ requested capabilities ∩ capability ceiling`

A task that requests fewer capabilities than permitted SHOULD receive only the requested subset.

A task that requests capabilities beyond the ceiling MUST NOT receive them automatically. Atlas MAY reject the task, mark it blocked, or request an explicit expansion of authority.

Repository or project configuration MAY reduce an effective capability grant but MUST NOT enlarge an operator-owned capability ceiling.

Capability-bearing policy changes originating from an agent-writable workspace MUST NOT become authoritative merely because they are valid repository files. Adoption of an enlarged capability policy requires an explicit controller/operator transition.

## 7. Security capabilities versus orchestration roles

Security capabilities SHOULD be represented independently from orchestration or methodological roles.

Roles such as:

* implementation;
* patch review;
* state audit;
* future planner or synthesis roles;

MAY provide default capability requests, but their names MUST NOT themselves constitute security authority.

For example:

* implementation will normally request workspace write access;
* patch review will normally request read-only workspace access;
* state audit will normally request read-only workspace access.

The effective grant remains determined by security policy.

Changing models, reasoning effort, session freshness, role names or orchestration strategy MUST NOT implicitly enlarge capabilities.

## 8. Filesystem and process execution

Implementation agents may receive write access to the designated project workspace.

By default they MUST NOT receive unrestricted write access to the remainder of the user's home directory or system.

Read-only agents such as reviews and audits SHOULD receive read-only workspace access.

Repository metadata such as `.git` SHOULD remain outside ordinary implementation-agent write authority where practical. Atlas Controller MAY retain separate authority for checkpoints, commits and workflow transitions.

Granting write access to a workspace necessarily allows an implementation agent to make incorrect or destructive changes within that writable scope. Protection and recovery of pre-existing workspace contents SHOULD therefore be addressed through workflow durability and recoverability mechanisms rather than being misrepresented as complete sandbox prevention.

Atlas MUST NOT invoke commands through avoidable shell interpolation when an argument-vector interface is available.

Privilege escalation, including `sudo`, MUST NOT be available to an agent by default.

Installing system software, modifying operating-system configuration or modifying unrelated repositories requires authority outside the normal implementation grant.

## 9. Network access

Network access is disabled by default for agent executions.

It may be enabled for an individual execution or class of executions when permitted by the capability ceiling.

Network access, private-data access and credential access are independent capabilities.

Enabling network access MUST NOT by itself expose:

* authentication tokens;
* SSH or agent sockets;
* credential helpers;
* connector credentials;
* cloud credentials;
* unrelated private files;
* ambient environment secrets.

Atlas does not require domain-level network allowlists as part of its baseline security model. Such controls MAY be introduced by specialized, credentialed, enterprise or hardened profiles when justified.

Review and state-audit operations SHOULD normally run without network access.

The effective absence of network access SHOULD be behaviorally testable rather than inferred only from configuration identity.

## 10. Credentials, environment and private data

Atlas SHOULD minimize credentials, environment data and private filesystem content visible to model-controlled execution.

Credentials MUST NOT deliberately be copied into prompts, execution reports or telemetry.

Agent-controlled processes SHOULD receive a deliberately constructed environment rather than unrestricted ambient operator state when practical.

External account authority MUST be granted independently from ordinary network capability.

Logs and telemetry SHOULD use explicit allowlists of recorded fields where practical.

Raw execution output MAY contain sensitive data and SHOULD therefore have explicit retention, access and size policies appropriate to its diagnostic value.

Atlas does not claim perfect secret detection or data-loss prevention. Avoiding unnecessary exposure is preferred over attempting complex post-hoc secret recognition.

## 11. Repository and external mutations

Normal implementation may modify the authorized working tree.

Atlas Agent MUST NOT, by default, receive authority to:

* push changes to remote repositories;
* force-push;
* rewrite published history;
* mutate unrelated external repositories;
* perform other external-account mutations.

Checkpoint, commit or reference mutation MAY occur through explicit Atlas Controller workflow operations.

Repository state SHOULD remain inspectable and recoverable using ordinary Git tooling.

Atlas security MUST NOT depend on making the repository unusable outside Atlas.

Natural-language instructions such as "do not push" are methodological guidance, not sufficient enforcement when the execution environment otherwise possesses the necessary network and credentials.

Remote mutation SHOULD therefore be controlled primarily through capability separation, especially network and credential availability.

## 12. Untrusted instructions and project configuration

Instructions discovered inside repository content, generated files, dependency documentation, model output or network resources are treated as untrusted input with respect to security authority.

They may provide task information but cannot override Atlas capability restrictions or operator-owned policy.

The same principle applies to machine-readable configuration discovered in a project.

Project-controlled configuration MAY affect behavior inside an already authorized envelope, but MUST NOT silently increase effective filesystem, network, credential, external-account, tool or privilege capabilities beyond the Atlas ceiling.

Where a downstream executor supports its own project-local configuration, hooks, MCP servers, execution rules or similar mechanisms, Atlas SHOULD ensure that those mechanisms cannot enlarge the effective Atlas grant.

Atlas SHOULD enforce prompt-injection resistance primarily through capability boundaries rather than attempting to perfectly classify malicious natural-language instructions.

## 13. Runtime and supply-chain integrity

Security and reproducible releases are separate concerns.

Atlas releases SHOULD identify compatible and tested versions of Atlas Agent and its executors.

Cryptographic hashes MAY be used when distributing, reproducing or verifying release artifacts.

Exact runtime identity MUST be security-protected when substitution of an artifact could enlarge the agent's effective capabilities or bypass an enforced boundary.

Assets that affect only:

* model behavior;
* methodology;
* diagnostics;
* reproducibility;
* compatibility metadata;

do not require security-style cryptographic pinning in the default profile solely because they influence an execution.

Prompts, model catalogues, profiles and similar assets MAY nevertheless be versioned or hashed when required for reproducibility and auditability.

Standard package-manager and release verification mechanisms are acceptable for the default local-development profile when artifact substitution cannot enlarge effective capabilities.

Stronger per-execution pinning MAY belong to a reproducibility or hardened profile when its operational cost is justified.

## 14. Reproducibility and assurance

Reproducibility SHOULD make it possible to identify or recover the significant source assets used for an execution or release.

A cryptographic digest proves identity only when the corresponding canonical bytes remain recoverable.

Versioned prompts, configuration, model catalogues and release assets MAY therefore be retained even when they are not security-critical.

Missing provenance or diagnostic evidence MAY prevent Atlas from making an assurance, qualification or release claim even when execution itself remains safe.

Atlas SHOULD distinguish:

* executor/process completion;
* task success;
* execution health;
* verification or qualification status.

A process exiting successfully MUST NOT automatically be treated as evidence that all requested model tool operations succeeded.

Structured executor/tool events SHOULD be preferred over parsing model prose when execution health is evaluated.

## 15. State integrity and crash recovery

Atlas SHOULD reliably detect corrupt workflow state and SHOULD make interrupted operations recoverable.

These are primarily correctness and durability requirements, not protection against a malicious local operator.

Checksums, atomic writes, journals, fsync operations and content identities MAY be used where their reliability or reproducibility benefit justifies their complexity.

Atlas MUST NOT claim cryptographic authentication from mechanisms designed only to detect accidental corruption, concurrent updates or internal inconsistency.

Telemetry completeness SHOULD NOT normally become a security prerequisite unless the missing information is itself required to determine whether an authority boundary was respected.

## 16. Failure policy

Atlas SHOULD fail closed when uncertainty affects actual authority, including:

* filesystem write scope;
* privilege level;
* credential visibility;
* external-account authority;
* network capability;
* effective tool capability;
* whether a requested grant exceeds its authorized ceiling.

Atlas SHOULD fail clearly rather than fail closed for ordinary non-security metadata, optional telemetry, diagnostics or provenance.

Loss of optional telemetry MUST NOT normally prevent otherwise safe development work.

Missing evidence MAY prevent an assurance or release qualification independently of whether execution was safe.

Security failures should identify the violated boundary and an actionable remediation rather than merely report inconsistent internal state.

## 17. Security versus methodology

Security policy MUST remain independent of model identity.

Choosing Luna, Sol, reasoning effort, session reuse, review methodology, checkpoint frequency or release cadence is an orchestration decision.

Instructions such as:

* inspect before editing;
* preserve unrelated changes;
* run relevant tests;
* do not broaden scope;
* produce concise factual reports;

are development methodology unless they correspond to independently enforced capabilities.

Security specifies what any selected agent is capable of doing, not what the model is merely instructed to avoid doing.

Changing models MUST NOT require redesigning Atlas's security model.

## 18. Complexity budget

Every significant security mechanism SHOULD be explainable by:

1. the asset being protected;
2. the credible in-scope threat;
3. the security property provided;
4. the implementation and operational cost;
5. a test demonstrating that the mechanism enforces that property.

A mechanism without a credible in-scope threat SHOULD normally be removed, simplified, reclassified as reliability/reproducibility machinery, or moved to an optional hardened profile.

Security improvements MUST be evaluated against portability, deployability, debuggability and maintainability.

Controls designed primarily against malicious same-UID replacement, hostile operators or compromised hosts SHOULD NOT become baseline requirements merely because they are technically possible.

## 19. Optional hardened profile

Atlas may later provide a hardened execution profile for scenarios such as:

* deliberately untrusted repositories;
* automated CI workers;
* shared infrastructure;
* external users;
* stronger supply-chain requirements;
* credential-bearing autonomous services.

Such a profile may add:

* stronger artifact pinning;
* stricter configuration provenance;
* network destination controls;
* isolated credentials;
* stronger filesystem or VM isolation;
* stricter hook/MCP restrictions;
* additional provenance and tamper-detection mechanisms.

Requirements of that profile MUST NOT silently become requirements of normal local Atlas development.
