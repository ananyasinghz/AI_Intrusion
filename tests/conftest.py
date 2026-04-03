"""Pytest boot — must load before test modules import backend.main."""
import os

os.environ.setdefault("SKIP_PIPELINE_LIFESPAN", "1")
