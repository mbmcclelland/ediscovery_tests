"""
mitmproxy addon — captures Digital Reef REST API calls.

Run standalone:
    source .venv/bin/activate
    mitmdump -s proxy_logger.py \
             --listen-host 0.0.0.0 --listen-port 8080 \
             --set ssl_insecure=true

Then configure your browser proxy to 192.168.58.128:8080.
Captures are written to /tmp/dr_proxy_capture.json after every response.
"""
from mitmproxy import http, ctx
import json
from datetime import datetime

OUTPUT   = "/tmp/dr_proxy_capture.json"
DR_REST  = "/ediscovery/rest/"

class DrApiLogger:
    def __init__(self):
        self.calls = []

    def response(self, flow: http.HTTPFlow) -> None:
        if DR_REST not in flow.request.pretty_url:
            return

        endpoint = flow.request.pretty_url.split(DR_REST, 1)[-1]
        entry = {
            "ts":             datetime.utcnow().isoformat(),
            "endpoint":       endpoint,
            "method":         flow.request.method,
            "request_body":   None,
            "status":         flow.response.status_code,
            "response_body":  None,
        }

        if flow.request.content:
            try:
                entry["request_body"] = json.loads(flow.request.text)
            except Exception:
                entry["request_body"] = flow.request.text[:4000]

        if flow.response.content:
            try:
                entry["response_body"] = json.loads(flow.response.text)
            except Exception:
                entry["response_body"] = flow.response.text[:4000]

        self.calls.append(entry)
        ctx.log.info(f"[DR] {entry['method']:4s} {endpoint} → {entry['status']}")

        with open(OUTPUT, "w") as f:
            json.dump(self.calls, f, indent=2, default=str)


addons = [DrApiLogger()]
