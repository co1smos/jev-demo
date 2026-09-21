import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def configuration():
    return {
        "alpaca": "configured"
        if os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_API_SECRET")
        else "missing",
        "typesafe": "configured" if os.environ.get("TYPESAFE_API_KEY") else "missing",
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        config = configuration()
        if self.path == "/health":
            body = json.dumps(
                {
                    "status": "ok" if "missing" not in config.values() else "configuration_required",
                    "configuration": config,
                }
            ).encode()
            content_type = "application/json"
        elif self.path == "/":
            status = "Ready" if "missing" not in config.values() else "Configuration required"
            body = (
                "<!doctype html><html lang=en><meta charset=utf-8>"
                "<meta name=viewport content='width=device-width,initial-scale=1'>"
                f"<title>JEV Simulator</title><h1>JEV Simulator</h1><h2>{status}</h2>"
                f"<p>Alpaca: {config['alpaca']}</p><p>TypeSafe: {config['typesafe']}</p>"
            ).encode()
            content_type = "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.environ.get("JEV_DEMO_PORT", "8000"))
    print(f"JEV Simulator listening on http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
