# First Run

**Your README works on your laptop. Does it work for someone new?**

A Claude Code skill and a small Python verifier for the path from a repository's documented quickstart to its first visible result. First Run preserves the first failure, proposes a minimal fix, and checks a separate fresh replay. Useful for maintainers, SDK authors, agency handovers and owners of AI-built projects.

## A ten-second example

This repository includes a synthetic Python project whose README says `python app.py`, while its tracked file is `hello.py`.

| Stage | Evidence | Outcome |
|---|---|---|
| Baseline | README.md:4, `python app.py` | FAILED: file is missing |
| Proposed patch | Change one command to `python hello.py` | Reviewable one-line diff |
| Fresh repair replay | New tracked commit, empty export, same success assertion | VERIFIED: `Hello, newcomer!` |

The original failure remains a failure. The repair gets its own evidence. The automated test performs this sequence rather than comparing canned report headings.

## Install in Claude Code

Copy `skills/first-run/` into `~/.claude/skills/first-run/` (personal), or `.claude/skills/first-run/` inside the project. Keep the scripts and references alongside `SKILL.md`.

Start a Claude Code session and invoke explicitly:

```text
/first-run /path/to/local/repository
```

The skill is intentionally user-invoked (`disable-model-invocation: true`) and does not preapprove tools. Claude Code's host permissions still apply. Review unfamiliar code and use real isolation before executing it. Installing this skill is not authorization to install project dependencies or execute arbitrary repositories.

## Portable CLI

Requirements: Python 3.10+ and Git. Node is needed only for Node projects. No pip packages, browser, paid API or Claude account is needed for the CLI.

Author a [command contract](skills/first-run/references/contract.md) from the actual README. Then run:

```sh
python skills/first-run/scripts/first_run.py /path/to/repo contract.json --out ./baseline
```

This defaults to a **BLOCKED static-only report**. After the host has approved execution of reviewed trusted code, add `--execute-reviewed`. That flag records an operator decision; it cannot grant permission or provide isolation. Do not use it to bypass the host.

The output directory must be new and outside the target repo. It contains readable `report.md` and machine-readable `evidence.json`. The contract holds ordered commands, exact documentation lines, working directories and explicit success assertions. Evidence holds commit and contract hashes, actual exit codes, assertion results and output hashes. Raw output is deliberately not retained; inspect diagnostics privately and add a reviewed explanation when necessary.

The skill additionally delivers a proposed patch and separate repair artifacts when a repair is justified and execution is available. The CLI does not invent a patch or automatically edit your repository.

## Verify the distribution

```sh
python -m unittest discover -s tests -v
```

Tests create only synthetic temporary repositories and run tiny local greeting programs. They cover the broken baseline, minimal repair, fresh replay, first-failure stop, static mode, stale citations, missing runtime, wrong directory, external requirements, path traversal, output privacy and a passing Node example (skipped if Node is unavailable).

The release was tested on Windows with Python 3.12.14, Node 24.19.0 and Git 2.53.0. Other operating systems and an actual Claude Code session have not been tested here. The Python CLI is standard-library code; that is not a claim of verified compatibility with every agent or platform.

## Scope and honest limits

The helper exports tracked HEAD blobs. It does **not** test clone transport or authentication and excludes untracked/local setup. This is a reproducibility boundary, not a security sandbox. Symlinks/submodules, shell pipelines, dependency installation, long-lived servers and external-account workflows require a separately approved isolated/manual replay. A timeout terminates the direct child, not necessarily descendants. Output hashes are not a comprehensive secret scanner: contracts, paths and excerpts still need review before sharing.

“Verified” applies only to the recorded commands, assertions and tested environment. Missing prerequisites are “blocked”; executed failures are “failed.” No repair is smuggled into baseline evidence. See [the protocol](skills/first-run/references/protocol.md).

Other tools address onboarding and documentation audits, including Browserbase's agent-experience skill and Skillstead's docs-claim-check. First Run focuses on ordered command replay, a minimal proposed patch, and a second clean verification. It does not claim to be the first onboarding auditor or a replacement for those broader workflows.

## Design references

Reviewed 2026-10-19: [Claude Code skills documentation](https://code.claude.com/docs/en/skills) for installation and invocation controls; [Anthropic's Agent Skills engineering article](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) for the skill-plus-focused-resources structure. Implementation and synthetic examples here are original.

MIT, see [LICENSE](LICENSE). No adoption, star or download claims are made.

---

Built by Kamesh Jindal at [OMX Digital](https://omxdigital.ai). Part of the [OMX Claude Skills toolkit](https://github.com/OmxKamesh/claude-code-skills). Need this set up for your business? [kamesh@omxdigital.ai](mailto:kamesh@omxdigital.ai)
