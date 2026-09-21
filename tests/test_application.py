import json
import os
import socket
import subprocess
import sys
import time
import unittest
from urllib.request import urlopen


class ApplicationTests(unittest.TestCase):
    def test_process_serves_health_and_page_without_exposing_secrets(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        env = os.environ.copy()
        secrets = ["typesafe-secret", "alpaca-key-secret", "alpaca-secret-secret"]
        env.update(
            JEV_DEMO_PORT=str(port),
            TYPESAFE_API_KEY=secrets[0],
            ALPACA_API_KEY=secrets[1],
            ALPACA_API_SECRET=secrets[2],
        )
        env.pop("ALPACA_API_SECRET")
        process = subprocess.Popen(
            [sys.executable, "-m", "jev_demo"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            for _ in range(50):
                try:
                    with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.2) as response:
                        health_text = response.read().decode()
                    break
                except OSError:
                    if process.poll() is not None:
                        self.fail(process.stdout.read())
                    time.sleep(0.02)
            else:
                self.fail("application did not start")

            with urlopen(f"http://127.0.0.1:{port}/", timeout=1) as response:
                page = response.read().decode()

            self.assertEqual(
                {
                    "status": "configuration_required",
                    "configuration": {
                        "alpaca": "missing",
                        "typesafe": "configured",
                    },
                },
                json.loads(health_text),
            )
            self.assertIn("Configuration required", page)
            self.assertIn("Alpaca: missing", page)
            self.assertIn("TypeSafe: configured", page)
            self.assertFalse(any(secret in health_text + page for secret in secrets))
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=2)
            output = process.stdout.read()
            process.stdout.close()
            self.assertFalse(any(secret in output for secret in secrets))


if __name__ == "__main__":
    unittest.main()
