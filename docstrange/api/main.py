"""FastAPI application entry point.

Run with:
    uvicorn docstrange.api.main:app --reload --port 8000

Then visit http://localhost:8000/docs for the interactive API explorer.
"""

from .routes import create_app

app = create_app()
