# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

To report a security vulnerability, use [GitHub's private security advisory feature](https://github.com/your-org/executionkit/security/advisories/new).

Alternatively, email the maintainers directly. Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

**Response SLA:**
- Acknowledgement within 48 hours
- Assessment within 7 days
- Fix or mitigation within 30 days for critical issues

## Security Considerations

### LLM Output is Untrusted

ExecutionKit passes LLM-generated content to evaluators and tools. Treat all LLM outputs as untrusted:

- **Never `eval()` LLM output** — use AST-based safe evaluators for math expressions
- **Validate tool arguments** against their JSON Schema before execution
- **Sanitize tool observations** before logging or displaying to end users

### API Key Handling

- Store API keys in environment variables, not source code
- The `Provider` class accepts `api_key=""` for keyless endpoints (e.g. local Ollama)
- API keys may appear in `Provider.__repr__` — avoid logging provider instances in production

### Prompt Injection

The `refine_loop` default evaluator interpolates generated content into evaluation prompts. Use structured output mode or explicit delimiters when evaluating untrusted content.

### Tool Execution

Tools execute arbitrary async Python functions. Ensure tool implementations validate their own inputs and have appropriate resource limits.
