# Publishing i3x-client to PyPI

## Prerequisites

- A [PyPI account](https://pypi.org/account/register/)
- An API token from [PyPI token management](https://pypi.org/manage/account/token/)
- Build tools installed in your venv: `pip install build twine`

## Making Changes

1. Activate the venv:

   ```bash
   cd ~/Projects/i3x-python
   source .venv/bin/activate
   ```

2. Make your code changes.

3. Run the tests:

   ```bash
   pytest tests/ -v
   ```

4. Bump the version in **both** of these files (they must match):

   - `pyproject.toml` — the `version` field
   - `src/i3x/__init__.py` — the `__version__` string

   PyPI rejects uploads for versions that already exist. You must bump the version every time you publish, even for metadata-only changes.

## Building

1. Remove any previous build artifacts:

   ```bash
   rm -rf dist
   ```

2. Build the sdist and wheel:

   ```bash
   python -m build
   ```

3. Validate the artifacts:

   ```bash
   twine check dist/*
   ```

   Both the `.tar.gz` and `.whl` should show `PASSED`.

## Testing with TestPyPI (Optional)

If you want to verify the package before publishing to the real PyPI:

1. Create a [TestPyPI account](https://test.pypi.org/account/register/) and API token.

2. Upload to TestPyPI:

   ```bash
   twine upload --repository testpypi dist/*
   ```

3. Install from TestPyPI to verify:

   ```bash
   pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ i3x-client
   ```

   The `--extra-index-url` flag pulls runtime dependencies (`httpx`, etc.) from real PyPI since they won't exist on TestPyPI.

## Publishing to PyPI

```bash
twine upload dist/*
```

When prompted:
- **Username:** `__token__`
- **Password:** your PyPI API token (starts with `pypi-`)

## Saving Credentials

To avoid entering credentials each time, create `~/.pypirc`:

```ini
[pypi]
username = __token__
password = pypi-YOUR-TOKEN-HERE

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-YOUR-TEST-TOKEN-HERE
```

## Verifying the Release

After uploading, confirm it works:

```bash
pip install --upgrade i3x-client
python -c "import i3x; print(i3x.__version__)"
```

The package page will be at: https://pypi.org/project/i3x-client/
