# Security Policy

## Supported versions

| Version | Security fixes |
|---|---|
| 0.3.x | Yes |
| 0.2.x and earlier | No |

Upgrade to the newest 0.3.x release before reporting a defect that may already
be fixed.

## Report a vulnerability

Do not open a public issue for a suspected vulnerability. Use
[GitHub private security advisories](https://github.com/tafreeman/executionkit/security/advisories/new)
to send the report to the maintainer.

Include:

- the affected version or commit;
- the smallest reproducible example;
- the security impact;
- any conditions required to trigger the issue; and
- a suggested fix, if you have one.

Do not include working credentials, private endpoint URLs, or unrelated user
data.

## Security model

ExecutionKit runs inside the caller's Python process. It sends prompts to a
configured model endpoint and may execute async Python tools registered by the
caller. The package does not isolate the process, authenticate end users, or
authorize application-level actions.

The main trust boundaries are:

1. caller code to the configured model endpoint;
2. model output to parser and pattern code;
3. model-requested arguments to registered tools;
4. caller-owned callbacks for traces, approvals, checkpoints, and evaluators;
   and
5. serialized state returned to caller-owned storage.

## Credentials and provider responses

- Pass credentials through environment variables or a secret manager.
- `Provider.__repr__` masks its configured `api_key`.
- Library-owned provider error messages apply best-effort credential-pattern
  redaction. Redaction is not a substitute for safe logging.
- `LLMResponse.raw` contains the unmodified provider payload. ExecutionKit does
  not log it, but caller code must redact it before logging or tracing.
- Trace callbacks are caller-owned. Review the payload before forwarding it to
  a third-party telemetry service.
- `Provider` accepts HTTP and HTTPS URLs so local endpoints work. Use HTTPS for
  remote endpoints and enforce any host allowlist in the calling application.

Avoid logging environment dumps, request headers, raw exception objects from
custom transports, tool arguments, or complete model transcripts.

## Model output

Treat every model response as untrusted input.

- `structured()` parses JSON and can run a caller-supplied validator. A parsed
  value is not automatically safe or authorized.
- The default `refine_loop()` evaluator uses delimiters and truncation to
  reduce prompt-injection risk. It is still an LLM-based evaluator, not a
  security control.
- Provider-reported token counts are range-checked before they enter budget
  accounting.
- Do not call `eval()`, `exec()`, or a shell with model-generated text.

Use deterministic application checks for permissions, money movement, data
access, and other high-impact decisions.

## Tool execution

`react_loop()` validates the model-to-tool boundary, but registered tools are
normal Python callables with the permissions of the current process.

The loop:

- rejects duplicate tool names before the first provider call;
- checks arguments with a built-in JSON Schema subset;
- fails closed on unsupported schema features unless the `jsonschema` extra is
  installed;
- limits rounds and tool calls per round;
- applies a timeout to each tool call;
- truncates tool observations; and
- returns only an exception type to the model when a tool raises.

The caller must still:

- validate domain rules inside each tool;
- authenticate and authorize the current user;
- set time, size, and rate limits appropriate for the operation;
- use `ApprovalGate` before side effects that require review; and
- isolate untrusted tool implementations in another process or container.

Approval callbacks and tool code can themselves fail or leak data. Treat them
as application code, not as a package sandbox.

## Checkpoints and serialization

`WorkflowCheckpoint.to_dict()` returns plain Python data, but step outputs may
contain caller-defined objects. Validate checkpoint contents before
serializing them, and do not load untrusted pickle data.

The caller owns checkpoint confidentiality, integrity, retention, and access
control.

## Dependencies and releases

The base package has no required third-party runtime dependencies. Optional
extras and development tools still need normal vulnerability management.

Repository checks include:

- Bandit for Python source scanning;
- `pip-audit` against `requirements.lock`;
- CodeQL;
- dependency updates through Dependabot;
- private-key and secret scanning in pre-commit hooks; and
- PyPI trusted publishing for releases.

These checks reduce risk but do not prove that the package is free of
vulnerabilities.
