# Fly.io Deployment Guide

This guide shows how to run the DocStrange web interface on [Fly.io](https://fly.io) and keep the workflow friendly for local testing.

## Prerequisites

- A Fly.io account and the [`flyctl`](https://fly.io/docs/hands-on/install-flyctl/) CLI installed locally.
- Docker installed locally if you want to build images on your machine. (Fly will also build in its remote builders.)
- Python 3.11+ if you plan to run scripts locally before deploying.
- Optional: A `NANONETS_API_KEY` if you want to use DocStrange's managed cloud extraction mode. Local CPU/GPU extraction works without it.

## 1. Clone the repository

```bash
git clone https://github.com/NanoNets/docstrange.git
cd docstrange
```

## 2. Review the Docker image

The included [`Dockerfile`](../../Dockerfile) installs all OCR dependencies (Poppler, Tesseract, and the OpenGL runtime libraries required by EasyOCR) and launches the Flask application with Gunicorn. Adjust the base image or dependency list if you need GPU support.

If you want to verify the container locally before deploying to Fly.io:

```bash
docker build -t docstrange:local .
docker run --rm -p 8080:8080 docstrange:local
```

Then visit <http://localhost:8080> to access the drag-and-drop UI.

## 3. Launch a Fly.io app

Use `flyctl` to create (or link) an application. The provided [`fly.toml`](../../fly.toml) has sane defaults for a single shared-CPU machine.

```bash
flyctl launch --name <your-app-name> --copy-config --no-deploy
```

- Choose a region close to you (defaults to `iad` in the template).
- The `--copy-config` flag tells `flyctl` to reuse the committed `fly.toml`.
- `--no-deploy` lets you review everything before the first deploy.

Update `app` (and optionally `primary_region`) in `fly.toml` after running `flyctl launch`.

## 4. Configure secrets (optional)

If you want to use DocStrange's cloud mode, store the API key as a Fly secret:

```bash
flyctl secrets set NANONETS_API_KEY=your_api_key_here
```

You can add other environment variables in the same way.

## 5. Deploy to Fly.io

```bash
flyctl deploy
```

Fly.io will build the Docker image, provision a machine, and release it. Once the command finishes you'll see the deployed URL. By default the Gunicorn server listens on `0.0.0.0:8080`, which Fly maps to HTTPS.

## 6. Test the app locally via Fly proxy

To exercise the remote app locally without exposing it publicly, use Fly's proxy capability:

```bash
flyctl proxy 8080
```

This forwards `localhost:8080` to your Fly app's internal port so you can use the UI or call the `/api/extract` endpoint from local scripts.

## 7. Tear down resources

When you're done testing:

```bash
flyctl apps destroy <your-app-name>
```

or scale to zero:

```bash
flyctl scale count 0
```

This stops billing while keeping the configuration around for future tests.

## Troubleshooting

- **Large model downloads** – The first request triggers model downloads. Keep the machine alive or bake models into a custom image if startup latency is a concern.
- **GPU mode** – Fly Machines with GPUs are required for GPU extraction. Update the Dockerfile to include CUDA dependencies and change the `[[vm]]` section in `fly.toml` to request a GPU instance.
- **File size limits** – The web app rejects uploads larger than 100 MB (`MAX_CONTENT_LENGTH`). Adjust `app.config['MAX_CONTENT_LENGTH']` in `docstrange/web_app.py` if needed.

With these steps you can iterate locally using the Fly.io deployment while still benefiting from the hosted environment.
