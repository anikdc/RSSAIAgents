"""
Secrets compatibility shim.

On Streamlit Community Cloud, API keys are stored in st.secrets from the
dashboard's Secrets panel. Locally, they live in a .env file loaded by
python-dotenv.

This module copies st.secrets entries into os.environ so every agent's
existing os.getenv("GEMINI_API_KEY") calls work in both environments without
code changes in those modules.

Call load_secrets() once at app startup before any agent is instantiated.
"""

import logging
import os


logger = logging.getLogger(__name__)


def load_secrets():
    """
    1. Try loading from .env for local development.
    2. Overlay any values from st.secrets for Streamlit Cloud.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv()
        logger.info("Loaded .env file (local mode).")
    except ImportError:
        pass

    try:
        import streamlit as st

        for key, value in st.secrets.items():
            if isinstance(value, str):
                os.environ[key] = value
        logger.info("Loaded secrets from st.secrets (cloud mode).")
    except Exception:
        pass
