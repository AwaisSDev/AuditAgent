# Publishing to PyPI

Both `sdk/` (published as `AudAgent`) and `mcp-server/` (published as
`auditagent-mcp`) publish via `.github/workflows/publish-pypi.yml`, using
PyPI's [Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
(OIDC) — no PyPI token is stored anywhere, in GitHub or otherwise.

## One-time setup (per package, do this once)

For each of the two projects on pypi.org, while logged in as an owner:

1. Go to `https://pypi.org/manage/project/<AudAgent-or-auditagent-mcp>/settings/publishing/`
2. Under "Add a new publisher", choose GitHub and fill in:
   - Owner: `AwaisSDev`
   - Repository name: `AuditAgent`
   - Workflow filename: `publish-pypi.yml`
   - Environment name: leave blank
3. Save.

Do this for both `AudAgent` and `auditagent-mcp`.

## Publishing a new version

1. Bump the version in the package's `pyproject.toml` (and `__init__.py`'s
   `__version__` for the sdk), commit and push.
2. Run the workflow: Actions tab → "Publish to PyPI" → Run workflow → pick
   `sdk` or `mcp-server`. Or via the CLI:
   ```
   gh workflow run "Publish to PyPI" -f package=mcp-server
   ```

PyPI never allows overwriting an existing version number — if a build
fails after a version is already live, bump again rather than retrying
the same version.
