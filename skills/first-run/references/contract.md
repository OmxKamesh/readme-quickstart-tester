# Ordered command contract, version 1

```json
{
  "version": 1,
  "phase": "baseline",
  "steps": [{
    "id": "hello",
    "source": {"path": "README.md", "line": 4, "text": "python hello.py"},
    "argv": ["python", "hello.py"],
    "cwd": ".",
    "timeout": 15,
    "assert_stdout": "Hello, newcomer!",
    "requirements": []
  }]
}
```

Each step cites exact tracked documentation text at its one-based start line. `argv` is an array, never a shell string; `cwd` is relative to the export. Paths use forward slashes and cannot escape the root. `assert_stdout` is a nonempty expected substring chosen from the documented first result, not from whatever the command happened to print. Exit zero AND the assertion must pass. The helper is deliberately limited to short, terminating commands with stdout assertions; use manual equivalent evidence for file, HTTP or interactive assertions.

List unsatisfied requirements such as `Node >= 20 unavailable`, `dependency installation needs host approval`, `ACME_API_KEY required` or `external account required`. Any listed requirement blocks execution. Never put secret values in the contract. Removing a requirement is a human/agent-reviewed change backed by evidence, not automatic remediation.

Record shell translation and runtime versions in the surrounding report. Do not split a pipeline into unrelated commands and claim equivalence. Commands cannot rely on shell activation or exported environment persisting across steps; unsupported semantics require isolated manual replay or a blocked report. The helper strips most inherited environment variables and uses a temporary home. This may deliberately expose hidden local configuration dependencies.

Exit codes: 0 verified, 1 command/assertion failure, 2 blocked or invalid input. JSON distinguishes blocked execution from invalid input (invalid input emits an argument error and no report). Evidence includes source, argv, cwd, commit, contract digest, exit code and output digests. Raw stdout/stderr are not saved. Inspect diagnostics privately when investigating, then add a reviewed summary to the report. Contracts and citations can still contain secrets: review before sharing.
