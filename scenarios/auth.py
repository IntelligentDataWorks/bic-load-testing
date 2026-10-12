"""Shared bearer-token auth for every scenario User class.

BIC_AUTH_TOKEN is read from the environment only -- never from a tracked file.
Populate it with a short-lived Databricks OAuth U2M access token (see
scripts/get-databricks-token.ps1) when testing a deployed app that enforces
auth. Leave it unset to hit an unauthenticated local FastAPI instance -- that
is what separates the no-auth local runs from the authenticated deployed runs.
"""

import os

from locust import HttpUser


class TokenAuthHttpUser(HttpUser):
    abstract = True

    def on_start(self):
        token = os.getenv("BIC_AUTH_TOKEN")
        if token:
            self.client.headers["Authorization"] = f"Bearer {token}"
