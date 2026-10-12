"""Headless render check for the control centre.

Runs the real entry point with Streamlit's ``AppTest`` and switches through every
page, so an import error, a bad Material icon name or a widget misuse fails here
instead of in the browser.

    .venv\\Scripts\\python.exe tools/render_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "streamlit_app.py"

PAGES = [
    "app_pages/dashboard.py",
    "app_pages/configure.py",
    "app_pages/authentication.py",
    "app_pages/run_test.py",
    "app_pages/live_logs.py",
    "app_pages/results.py",
    "app_pages/diagnosis.py",
    "app_pages/history.py",
    "app_pages/help.py",
]


def report(label: str, app: AppTest) -> bool:
    if app.exception:
        print(f"FAIL {label}")
        for exc in app.exception:
            first = (exc.value or "").splitlines()
            print("     ", first[0] if first else exc)
            for line in (exc.stack_trace or [])[-6:]:
                print("      ", line.rstrip())
        return False
    titles = [t.value for t in app.title] + [h.value for h in app.header]
    print(
        f"ok   {label:34} titles={titles[:2]} "
        f"buttons={len(app.get('button'))} errors={len(app.error)}"
    )
    for err in app.error:
        print("      st.error:", str(err.value)[:140])
    return True


def main() -> int:
    ok = True
    app = AppTest.from_file(str(ENTRY), default_timeout=180)
    app.run()
    ok &= report("streamlit_app.py (default page)", app)

    for page in PAGES:
        app = AppTest.from_file(str(ENTRY), default_timeout=180)
        app.run()
        app.switch_page(page)
        app.run()
        ok &= report(page, app)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
