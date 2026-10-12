"""One-user, one-endpoint gate: confirms /api/healthz returns 200 before any
run is allowed to scale up to load-test concurrency. Uses the same
BIC_AUTH_TOKEN bearer header as the other scenarios -- see auth.py.

    locust --config config/locust.deployed-smoke.conf
"""

from locust import constant, task

from auth import TokenAuthHttpUser


class HealthzSmokeUser(TokenAuthHttpUser):
    wait_time = constant(1)

    @task
    def check_healthz(self):
        with self.client.get("/api/healthz", name="/api/healthz", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"unexpected status {resp.status_code}: {resp.text[:200]}")
                return
            resp.success()
