# Publishing to PyPI

Target distribution: **`polars_ta_lib_extension`**
(PyPI canonical name: `polars-ta-lib-extension`).
Python import name: **`polars_ta_lib`**.

The workflow is [`.github/workflows/publish.yml`](.github/workflows/publish.yml).
It uses PyPI Trusted Publishing: no PyPI API token is stored in GitHub.

## 0. Before you start

The first release is already on PyPI:
https://pypi.org/project/polars-ta-lib-extension/

- PyPI release `0.1.0` exists and is immutable.
- Future versions require bumping `Cargo.toml` (`pyproject.toml` reads it dynamically).
- Local metadata check:

```bash
maturin build --sdist --out dist
twine check dist/*
```

## 1. Create a PyPI account

- https://pypi.org/account/register/

Verify your email and enable two-factor authentication.

## 2. Configure Trusted Publishing

Open https://pypi.org/manage/account/publishing/ and add a pending publisher:

| Field | Value |
|---|---|
| PyPI Project Name | `polars_ta_lib_extension` |
| Owner | `huangbogeng` |
| Repository name | `polars-ta-lib` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

The workflow name must match the file name exactly: `publish.yml`.

## 3. Create the GitHub environment

Settings → Environments → New environment → `pypi`.

You may add required reviewers for an extra approval step. No secrets are
needed; the workflow requests an OIDC token with `id-token: write`.

## 4. Publish

GitHub → Actions → **Publish** → Run workflow (branch `main`).

Or:

```bash
gh workflow run publish.yml
```

The workflow builds:

- Linux x86_64, manylinux_2_17
- macOS arm64 and x86_64
- Windows x86_64
- sdist

Then it runs `twine check` and uploads to PyPI.

## 5. Verify

```bash
pip install polars_ta_lib_extension
```

```python
import polars as pl
import polars_ta_lib as pta

print(pl.DataFrame({"close": [1.0, 2.0, 3.0]}).select(pta.sma(time_period=2)))
```

The distribution name is `polars_ta_lib_extension`; the import name remains
`polars_ta_lib`.

## 6. Versioning rules

PyPI versions are immutable. To publish a change:

1. Bump `version` in `Cargo.toml`.
2. Update `CHANGELOG.md`.
3. Commit and push.
4. Create tag `vX.Y.Z` and a GitHub release.
5. The release triggers the publish workflow.

Never reuse a version.

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

Do not commit tokens.

## 8. Troubleshooting

| Error | Cause |
|---|---|
| `invalid-publisher` | Owner/repo/workflow/environment does not match the pending publisher |
| `File already exists` | Version already uploaded; bump the version |
| `twine check` fails | README/metadata issue; fix before uploading |
| Linux wheel rejected on older glibc | Use the CI wheel built with manylinux_2_17, not a local manylinux_2_34 wheel |
| macOS install fails | Check the universal2 wheel was built |
