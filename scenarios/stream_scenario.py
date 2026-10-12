"""Separate scenario for POST /api/chat/stream.

SSE responses don't fit the normal request/response timing model: the
terminal {"type": "result"} event (same payload shape as ChatResult) can
arrive tens of seconds after the connection opens, with progress events in
between. Run this file on its own so its metrics aren't averaged together
with the fast, single-shot calls in basic_scenario.py:

    locust -f scenarios/stream_scenario.py --headless -u 1 -r 1 -t 10s --host http://localhost:8000

Auth is the same shared BIC_AUTH_TOKEN bearer header as basic_scenario.py -- see auth.py.
"""

import json
import time

from locust import between, events, task

from auth import TokenAuthHttpUser

CHAT_QUERY = "What were last week's top selling products?"
REQUIRED_CHAT_RESULT_FIELDS = {"session_id", "user_query_id", "action"}


class BicApiStreamUser(TokenAuthHttpUser):
    """Measures /api/chat/stream separately: time-to-first-event and total stream duration."""

    wait_time = between(1, 3)

    @task
    def stream_chat(self):
        payload = {"query": CHAT_QUERY}
        start = time.perf_counter()
        first_event_at = None
        result_event = None
        error_message = None

        with self.client.post(
            "/api/chat/stream", json=payload, stream=True, name="/api/chat/stream", catch_response=True
        ) as resp:
            if resp.status_code != 200:
                error_message = f"unexpected status {resp.status_code}"
                resp.failure(error_message)
            else:
                try:
                    for raw_line in resp.iter_lines(decode_unicode=True):
                        if not raw_line:
                            continue
                        if first_event_at is None:
                            first_event_at = time.perf_counter()
                        line = raw_line[len("data:"):].strip() if raw_line.startswith("data:") else raw_line
                        try:
                            event = json.loads(line)
                        except ValueError:
                            continue
                        if event.get("type") == "error":
                            error_message = event.get("message", "stream reported an error")
                            break
                        if event.get("type") == "result":
                            result_event = event
                            break
                except Exception as exc:  # connection dropped mid-stream, etc.
                    error_message = str(exc)

                if error_message is None and result_event is None:
                    error_message = "stream ended without a terminal result event"

                chat_result = (result_event or {}).get("result") if result_event else None
                valid_result = isinstance(chat_result, dict) and REQUIRED_CHAT_RESULT_FIELDS <= chat_result.keys()

                if error_message is None and valid_result:
                    resp.success()
                else:
                    resp.failure(error_message or f"terminal event did not match ChatResult: {chat_result}")

        total_time_ms = (time.perf_counter() - start) * 1000
        ttfb_ms = ((first_event_at - start) * 1000) if first_event_at else total_time_ms

        # Custom metrics: these are what actually characterize SSE performance,
        # separate from the single aggregate entry self.client.post already recorded above.
        events.request.fire(
            request_type="SSE",
            name="/api/chat/stream:time_to_first_event",
            response_time=ttfb_ms,
            response_length=0,
            exception=None if first_event_at else Exception("no SSE events received"),
        )
        events.request.fire(
            request_type="SSE",
            name="/api/chat/stream:total_duration",
            response_time=total_time_ms,
            response_length=0,
            exception=None if error_message is None else Exception(error_message),
        )
