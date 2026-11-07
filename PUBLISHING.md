# Publishing to PyPI

Target project: **`polars_ta_lib`** (PyPI canonical name: `polars-ta-lib`).

The workflow is [`.github/workflows/publish.yml`](.github/workflows/publish.yml).
It uses PyPI Trusted Publishing: no PyPI API token is stored in GitHub.

## 0. Before you start

- The PyPI and TestPyPI names are currently unoccupied.
- Version is `0.1.0` (`Cargo.toml`; `pyproject.toml` reads it dynamically).
- The GitHub release `v0.1.0` and tag already exist.
- Local metadata check:

```bash
maturin build --sdist --out dist
twine check dist/*
```

Both the wheel and sdist must pass `twine check`.

## 1. Create accounts

Create accounts on both registries:

- https://pypi.org/account/register/
- https://test.pypi.org/account/register/

Verify your email and enable two-factor authentication. PyPI requires 2FA for
maintainers.

## 2. Configure Trusted Publishing

### TestPyPI first

Open https://test.pypi.org/manage/account/publishing/ and add a pending
publisher with exactly these values:

| Field | Value |
|---|---|
| PyPI Project Name | `polars_ta_lib` |
| Owner | `huangbogeng` |
| Repository name | `polars-ta-lib` |
| Workflow name | `publish.yml` |
| Environment name | `testpypi` |

### PyPI

Open https://pypi.org/manage/account/publishing/ and add a pending publisher:

| Field | Value |
|---|---|
| PyPI Project Name | `polars_ta_lib` |
| Owner | `huangbogeng` |
| Repository name | `polars-ta-lib` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

The workflow name must match the file name exactly: `publish.yml`.

## 3. Create GitHub environments

In the GitHub repository:

Settings → Environments → New environment

Create:

- `testpypi`
- `pypi`

You may add required reviewers to `pypi` for an extra approval step. No secrets
are needed; the workflow requests an OIDC token with `id-token: write`.

## 4. Publish to TestPyPI

GitHub → Actions → **Publish** → Run workflow:

- Branch: `main`
- Repository: `testpypi`

The workflow builds:

- Linux x86_64, manylinux_2_17
- macOS universal2
- Windows x86_64
- sdist

Then it runs `twine check` and uploads to TestPyPI.

Verify installation:

```bash
pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  polars_ta_lib==0.1.0
```

```python
import polars as pl
import polars_ta_lib as pta

print(pl.DataFrame({"close": [1.0, 2.0, 3.0]}).select(pta.sma(time_period=2)))
```

## 5. Publish to PyPI

After TestPyPI succeeds:

1. Make sure the PyPI pending publisher exists (step 2).
2. Run **Publish** again with repository `pypi`.

Or publish a GitHub release; the `release: published` trigger publishes to PyPI.

After success:

```bash
pip install polars_ta_lib
```

## 6. Versioning rules

PyPI versions are immutable. To publish a change:

1. Bump `version` in `Cargo.toml`.
2. Update `CHANGELOG.md`.
3. Commit and push.
4. Create tag `vX.Y.Z` and a GitHub release.
5. The release triggers the publish workflow.

Never reuse a version, on either PyPI or TestPyPI.

## 7. Manual fallback: API token

If OIDC is unavailable, use a scoped API token instead:

1. PyPI → Account settings → API tokens → Add API token.
2. Store it as the GitHub secret `PYPI_API_TOKEN`.
3. Upload with twine:

```bash
TWINE_USERNAME=__token__ \
TWINE_PASSWORD="$PYPI_API_TOKEN" \
twine upload dist/*
```

For TestPyPI add `-r testpypi` and use a TestPyPI token. Do not commit tokens.

## 8. Troubleshooting

| Error | Cause |
|---|---|
| `invalid-publisher` | Owner/repo/workflow/environment does not match the pending publisher |
| `File already exists` | Version already uploaded; bump the version |
| `twine check` fails | README/metadata issue; fix before uploading |
| Dependency resolution fails on TestPyPI | Use `--extra-index-url https://pypi.org/simple/` |
| Linux wheel rejected on older glibc | Use the CI wheel built with manylinux_2_17, not a local manylinux_2_34 wheel |
| macOS install fails | Check the universal2 wheel was built |
