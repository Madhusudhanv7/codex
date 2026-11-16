# circle-codex-cli-bin

Platform-specific Codex CLI runtime consumed by the `circle-codex` Python SDK.
Install `circle-codex`; this package is pulled in automatically.

This is an unofficial build of the Codex CLI from
<https://github.com/ashish447344/codex>, a fork of
<https://github.com/openai/codex> that adds a built-in xAI model provider. It is
not affiliated with, endorsed by, or supported by OpenAI or xAI.

It comes in two forms:

- Platform wheels with the Codex binaries inside, attached to the GitHub Release
  `circle-v<version>` of the repository above.
- A small `py3-none-any` wheel on PyPI that lists those platform wheels with
  their SHA-256 checksums. The first time the runtime is needed it downloads the
  wheel for the current platform, verifies it and unpacks it into a per-user
  cache. `python -m codex_cli_bin download` does this ahead of time.

`circle-codex-cli-bin` is intentionally wheel-only. Do not build or publish an
sdist for this package.
