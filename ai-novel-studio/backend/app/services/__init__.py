"""Business services.

Submodules are imported directly (``from app.services.project_service import
ProjectService``). This package deliberately re-exports nothing: eager imports
here would create an import cycle between the AI service, the model registry and
the services it depends on.
"""
