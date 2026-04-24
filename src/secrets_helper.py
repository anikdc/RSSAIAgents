"""
Secrets compatibility shim.

On Streamlit Community Cloud, API keys are stored in st.secrets (from the
dashboard's Secrets panel). Locally, they live in a .env file loaded by
python-dotenv.

This module copies st.secrets entries into os.environ so that every agent's
existing `os.getenv("GEMINI_API_KEY")` calls work in BOTH environments
without any code changes in those modules.

Call `load_secrets()` once at app startup (in app.py) BEFORE any agent
is instantiated.
"""

import os
import logging

logger = logging.getLogger(__name__)


def load_secrets():
    """
    1. Try loading from .env (works locally).
    2. Then overlay any values from st.secrets (works on Streamlit Cloud).
    
    st.secrets takes priority so the cloud dashboard always wins.
    """
    # --- Phase 1: .env (local) ---
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logger.info("Loaded .env file (local mode).")
    except ImportError:
        pass  # dotenv not installed — fine on cloud

    # --- Phase 2: st.secrets (cloud) ---
    try:
        import streamlit as st
        for key, value in st.secrets.items():
            if isinstance(value, str):
                os.environ[key] = value
        logger.info("Loaded secrets from st.secrets (cloud mode).")
    except Exception:
        # st.secrets not available or empty — fine locally
        pass
