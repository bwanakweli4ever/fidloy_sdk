# PyPI Trusted Publishing Checklist

Use this checklist to publish `fidloy` to PyPI from GitHub Actions without storing a PyPI API token in GitHub secrets.

## 1) Create package on PyPI

1. Sign in to https://pypi.org
2. Go to **Your projects** and create (or reserve by first upload) package name: `fidloy`

## 2) Configure Trusted Publisher on PyPI

In PyPI project settings, add a **Trusted Publisher** with:

- **Owner**: `mista-io`
- **Repository**: `Mista_B.I_pi`
- **Workflow file**: `fidloy_sdk/.github/workflows/publish-pypi.yml`
- **Environment name**: `pypi`

Save changes.

## 3) Ensure GitHub workflow matches

Workflow file: `fidloy_sdk/.github/workflows/publish-pypi.yml`

- Uses `permissions: id-token: write`
- Builds from `fidloy_sdk`
- Publishes via `pypa/gh-action-pypi-publish`
- Uses environment: `pypi`

## 4) Create release tag

Example for next version:

```bash
cd /Users/alexbwanakweli/Desktop/CodeHub/Mista_B.I_pi
git tag -a v0.2.0 -m "fidloy v0.2.0"
git push origin main
git push origin v0.2.0
```

## 5) Publish from GitHub Releases

1. Open repository releases page
2. Create release from tag (e.g. `v0.2.0`)
3. Publish release
4. GitHub Action runs automatically and uploads to PyPI

## 6) Verify installation

```bash
python -m pip install --upgrade fidloy
python -c "import fidloy_sdk; print('ok')"
```

## Optional: TestPyPI dry run

You can create a second workflow that publishes to TestPyPI first for validation.
