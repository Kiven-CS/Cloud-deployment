# Contributing

This project welcomes contributions and suggestions. Most contributions require you to agree to a Contributor License Agreement (CLA) declaring that you have the right to grant us the rights to use your contribution. For details, visit <https://cla.opensource.microsoft.com>.

This project follows the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).

## Development

Create and activate a virtual environment, then install the development dependencies:

```bash
cd src
python -m venv .venv
pip install -e ".[dev]"
```

Run the validation suite before opening a pull request:

```bash
ruff check .
ruff format --check .
pip-audit --requirement requirements.lock
```

Regenerate `requirements.lock` with `python -m piptools compile --strip-extras --no-emit-index-url --output-file=requirements.lock pyproject.toml` whenever runtime dependencies change.

Run `azd show` from the repository root and compile `infra/main.bicep` to validate template changes.
