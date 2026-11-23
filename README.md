# Hello, Azure Developer CLI with Python

This beginner-friendly template deploys a Python web app and its supporting resources to Azure. It demonstrates the standard Azure Developer CLI (`azd`) workflow with readable application and infrastructure code.

## Get started

Install [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd), then run:

```bash
azd init -t hello-azd-python
azd up
```

`azd up` prompts for your Azure subscription and location, provisions the resources, builds the container remotely, and deploys the app.

## What the template deploys

- An Azure Container App running FastAPI
- An Azure Container Apps environment
- An Azure Container Registry
- An Azure Storage account with an `attachments` blob container and `tickets` table
- A user-assigned managed identity
- Identity-based Blob and Table Storage access

The application includes a ticket form, optional file attachments, and a table of submitted tickets. No storage keys or connection strings are used.

> [!IMPORTANT]
> The deployed demo is publicly accessible and doesn't require users to sign in. Don't submit sensitive or production data, and run `azd down` when you finish exploring the template.

## Explore the template

- `azure.yaml` maps the Python project to the Container App and synchronizes resource endpoints for local development.
- `infra/main.bicep` composes the Azure resources and assigns access.
- `infra/core` contains one focused Bicep module for each resource type.
- `src/app/main.py` defines the FastAPI routes.
- `src/app/storage.py` uses the Azure SDK with `DefaultAzureCredential`.
- `src/app/templates` and `src/app/static` define the server-rendered UI.

## Run locally after deployment

The `postprovision` hook writes the non-secret Storage endpoints to `src/.env`. Your Azure developer identity supplies authentication.

```bash
cd src
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS or Linux
source .venv/bin/activate
```

Install and run the app:

```bash
pip install -e .
uvicorn app.main:app --reload
```

Open <http://localhost:8000>.

## Validate

```bash
cd src
pip install -e ".[dev]"
ruff check .
ruff format --check .
pip-audit --requirement requirements.lock
```

Runtime dependencies are pinned in `src/requirements.lock`. After changing dependencies in `pyproject.toml`, regenerate it from `src`:

```bash
python -m piptools compile --strip-extras --no-emit-index-url --output-file=requirements.lock pyproject.toml
```

## Clean up

Delete the Azure resources when you're finished:

```bash
azd down
```
