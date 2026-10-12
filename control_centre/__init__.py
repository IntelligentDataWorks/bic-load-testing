"""Control-centre backend for the BIC/IRIS load-testing Streamlit app.

The Streamlit pages under ``app_pages/`` stay thin: every piece of real logic --
profile discovery, validation, authentication, command construction, process
management, result parsing and LLM diagnosis -- lives in this package and is
importable/testable without Streamlit.
"""

from control_centre.paths import PROJECT_ROOT

__all__ = ["PROJECT_ROOT"]
