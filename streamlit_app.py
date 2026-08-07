"""Streamlit Community Cloud entrypoint.

The application remains implemented in app.py. Keeping this thin standard
entrypoint lets deployment routing change without duplicating UI or calculation
logic.
"""

from app import *  # noqa: F401,F403
