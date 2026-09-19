# Publishing to PyPI

Both `sdk/` (published as `tracyn`) and `mcp-server/` (published as
`tracyn-mcp`) publish via `.github/workflows/publish-pypi.yml`, using
PyPI's [Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
(OIDC) — no PyPI token is stored anywhere, in GitHub or otherwise.

## One-time setup (per package, do this once)

`tracyn` and `tracyn-mcp` are brand-new PyPI project names — there's no
existing project to add a publisher to yet, so this uses PyPI's
**pending publisher** flow instead of a project's own settings page:

1. While logged in to pypi.org, go to
   `https://pypi.org/manage/account/publishing/`
2. Under "Add a new pending publisher", fill in:
   - PyPI Project Name: `tracyn` (repeat this whole flow a second time for `tracyn-mcp`)
   - Owner: `AwaisSDev`
   - Repository name: `Tracyn`
   - Workflow filename: `publish-pypi.yml`
   - Environment name: leave blank
3. Save.

The project doesn't exist on PyPI until the first successful publish
through this pending publisher creates it — after that, its trusted
publisher lives at the normal
`https://pypi.org/manage/project/<name>/settings/publishing/` for any
future changes.

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
