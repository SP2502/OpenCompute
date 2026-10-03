# Security

OpenCompute runs models that can be tricked, and (later) gives them tools. The
most important security principle is:

> **The model is never the security boundary.**

Security must be enforced by deterministic software outside the model — file
permissions, path checks, and explicit limits — never by trusting what the model
says or outputs.

## Threat model (current milestone)

Even with only two capabilities, the main risks are:

1. **Prompt injection.** A webpage or search result can instruct the model to do
   something harmful. The model's "decision" is not trusted — the code checks
   the outcome.
2. **Path escape / arbitrary writes.** A plan or model output could try to write
   outside the workspace. Mitigated: the filesystem capability resolves paths and
   rejects anything outside the workspace root, and the planner's output is
   schema-validated (`extra="forbid"`).
3. **Untrusted web content.** Fetched pages are treated as data, never executed.
   They are only ever read as text and summarized.
4. **Arbitrary code execution.** Not present yet — there is no terminal/coding
   capability in Milestone 1. When one is added, it must run sandboxed with an
   explicit permission grant, not by default.
5. **Credential exposure.** The model key comes from the environment. The runtime
   itself does not log API keys — events store only model names and usage numbers.

## What is already enforced

- **Workspace confinement.** Files are written only under the workspace root.
  Absolute and `..` paths are rejected.
- **Schema validation.** Plans are parsed by Pydantic with extra fields forbidden,
  so an LLM cannot smuggle in unexpected structure.
- **Deterministic verification.** The verifier is plain code, not a second LLM
  that could be fooled the same way.

## What is intentionally NOT done yet

- No sandboxing or process isolation (no terminal/code capability exists yet).
- No fine-grained permission system (nothing sensitive is reachable yet).
- No rate limiting or network egress policy on fetches.
- No secret redaction in logs (keep model keys out of `OPENAI_*` if you log env).

These become real requirements the moment a code-execution or browser capability
is added, and are scheduled for Milestone 4.

## If you extend this

When you add a capability that can *do* something (code, browser, network, disk):

1. Give it a scoped permission, off by default.
2. Enforce that permission in code, not in a prompt.
3. Log every grant and denial to the event stream.
4. Sandbox it (Docker or better) before running untrusted input through it.
