"""Serving-endpoint smoke test: proves a single, non-streaming chitchat request
succeeds directly against the ds-insights-companion-agent-dev serving endpoint,
under the caller's own OAuth identity, before Genie/SQL routing or the BFF
layer are involved.

Reuses the shared TokenAuthHttpUser/BIC_AUTH_TOKEN (see auth.py) -- the
serving endpoint accepts the same bearer token as the workspace it lives in.

Request/response follow the MLflow ResponsesAgent contract confirmed from the
BFF: {"input": [...], "custom_inputs": {...}} in, {"output": [...],
"custom_outputs": {...}} out.
"""

import os
import uuid

from locust import task

from auth import TokenAuthHttpUser

DEFAULT_ENDPOINT_PATH = "/serving-endpoints/ds-insights-companion-agent-dev/invocations"
DEFAULT_RESPONSE_TIMEOUT_SECONDS = 180
DEFAULT_QUESTION = "Hello"
DEFAULT_SESSION_ID_PREFIX = "load_test"

# Overridable so the same scenario can be pointed at another serving endpoint
# without editing this file. Unset environment == the original behaviour.
ENDPOINT_PATH = os.getenv("BIC_SERVING_ENDPOINT_PATH", DEFAULT_ENDPOINT_PATH)
RESPONSE_TIMEOUT_SECONDS = int(
    os.getenv("BIC_REQUEST_TIMEOUT_SECONDS", str(DEFAULT_RESPONSE_TIMEOUT_SECONDS))
)


def _has_agent_error(body: dict) -> bool:
    if body.get("error"):
        return True
    output = body.get("output") or []
    return any(isinstance(item, dict) and item.get("type") == "error" for item in output)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be set to run the serving-endpoint smoke test")
    return value


class ServingEndpointSmokeUser(TokenAuthHttpUser):
    """Fires exactly one non-streaming chitchat request, then stops the user."""

    def on_start(self):
        super().on_start()
        # TokenAuthHttpUser only sets the header when a token is present -- without this check
        # a missing/expired BIC_AUTH_TOKEN would silently send an unauthenticated request instead
        # of failing with a clear reason.
        _require_env("BIC_AUTH_TOKEN")

    @task
    def invoke_once(self):
        user_id = _require_env("BIC_TEST_USER_ID")

        prefix = os.getenv("BIC_SESSION_ID_PREFIX", DEFAULT_SESSION_ID_PREFIX)
        session_id = f"{prefix}_{uuid.uuid4().hex}"
        question = os.getenv("BIC_TEST_QUESTION", DEFAULT_QUESTION)
        payload = {
            "input": [{"role": "user", "content": question}],
            "custom_inputs": {
                "session_id": session_id,
                "user_id": user_id,
            },
        }

        with self.client.post(
            ENDPOINT_PATH,
            json=payload,
            name=ENDPOINT_PATH,
            timeout=RESPONSE_TIMEOUT_SECONDS,
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                # Never log the token -- only status/body-shape details.
                hint = (
                    " -- BIC_AUTH_TOKEN is likely missing/expired in this shell; "
                    "re-run scripts/get-databricks-token.ps1 in the same terminal used for locust"
                    if resp.status_code == 401
                    else ""
                )
                resp.failure(f"unexpected status {resp.status_code}{hint}")
            else:
                try:
                    body = resp.json()
                except ValueError:
                    resp.failure("response was not valid JSON")
                    body = None

                if body is not None:
                    if not body.get("output"):
                        resp.failure("response had no non-empty 'output'")
                    elif _has_agent_error(body):
                        resp.failure("agent response contained an error")
                    else:
                        resp.success()

        # One invocation is the whole point of this smoke test.
        self.stop()
