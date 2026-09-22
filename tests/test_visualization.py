import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from jev_demo.__main__ import execute_run, simulation_identity
from jev_demo.historical_data import AlpacaHistoricalData, SYMBOLS
from jev_demo.read_model import visualization, comparison
from jev_demo.audit import read_audit, audit_csv
from jev_demo.run_store import RunStore


class FixtureProvider:
    def decide(self, state, model, question):
        action = 'HOLD'
        if state['symbol'] == 'AAPL':
            action = {330: 'BUY', 325: 'SELL'}.get(state['minutes_remaining'], 'HOLD')
        if state['symbol'] == 'MSFT':
            action = {324: 'ABSTAIN', 320: 'BUY'}.get(state['minutes_remaining'], 'HOLD')
        probabilities = dict.fromkeys(('BUY', 'HOLD', 'SELL', 'ABSTAIN'), .01)
        probabilities[action] = .50
        probabilities['HOLD' if action != 'HOLD' else 'BUY'] = .48
        return dict(model=model, action=action, probabilities=probabilities)


class VisualizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.store = RunStore(self.directory / 'runs.db')
        start = datetime(2026, 9, 18, 13, 30, tzinfo=timezone.utc)
        bars = {symbol: [dict(t=(start + timedelta(minutes=i)).isoformat(),
                             o=100+i/10, h=101+i/10, l=99+i/10, c=100.5+i/10, v=1000)
                         for i in range(390)] for symbol in SYMBOLS}
        def request(request):
            return json.dumps([dict(date='2026-09-18', open='09:30', close='16:00')]
                              if '/calendar?' in request.full_url else dict(bars=bars)).encode()
        self.data = AlpacaHistoricalData('fixture', 'fixture', self.directory, request=request,
                                        now=lambda: datetime(2026, 9, 19, tzinfo=timezone.utc))
        self.id = self.store.create({**simulation_identity('2026-09-18'), 'method': 'jev'})
        execute_run(self.store, self.id, '2026-09-18', self.data, FixtureProvider())

    def test_exact_snapshot_and_decision_execution_evidence(self):
        before = comparison(self.store, self.id)
        csv = audit_csv(read_audit(self.store, self.id))
        with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
            view = visualization(self.store, self.id, self.directory)
        self.assertEqual(self.id, view['run_id'])
        self.assertEqual(list(SYMBOLS), list(view['symbols']))
        self.assertEqual(self.store.read(self.id)['result']['source_digest'], view['source_digest'])
        for bars in view['symbols'].values():
            self.assertEqual(390, len(bars))
            self.assertEqual(sorted(b['timestamp'] for b in bars), [b['timestamp'] for b in bars])
        decisions = view['decisions']
        buy = next(d for d in decisions if d['action'] == 'BUY')
        self.assertEqual('2026-09-18T14:30:00Z', buy['minute'])
        self.assertEqual('2026-09-18T14:29:00Z', buy['reference_bar']['timestamp'])
        self.assertEqual(106.4, buy['reference_bar']['close'])
        self.assertEqual('2026-09-18T14:31:00Z', buy['fills'][0]['timestamp'])
        self.assertEqual('106.12122', buy['fills'][0]['price'])
        self.assertEqual(.5, buy['probabilities']['BUY'])
        self.assertTrue(any(d['action'] == 'SELL' for d in decisions))
        self.assertGreater(sum(d['action'] == 'HOLD' for d in decisions), 900)
        self.assertEqual(before, comparison(self.store, self.id))
        self.assertEqual(csv, audit_csv(read_audit(self.store, self.id)))

    def test_missing_corrupt_and_different_snapshot_fail_locally(self):
        path = next(self.directory.glob('*.json'))
        original = path.read_text()
        payload = json.loads(original)
        payload['bars'][0]['close'] += .01
        path.write_text(json.dumps(payload))
        with self.assertRaises(ValueError):
            visualization(self.store, self.id, self.directory)
        path.write_text(original)
        result = self.store.read(self.id)['result']
        for changes, changed_result in [({'trading_date': '2026-09-17'}, result),
                                        ({'symbols': ['AAPL']}, result),
                                        ({}, {**result, 'source_digest': '0' * 64})]:
            wrong = self.store.create({**simulation_identity('2026-09-18'), **changes, 'method': 'jev'})
            self.store.complete(wrong, changed_result)
            with self.assertRaises(ValueError):
                visualization(self.store, wrong, self.directory)
        path.unlink()
        with self.assertRaises(ValueError):
            visualization(self.store, self.id, self.directory)

    def test_http_visualization_and_historical_page_do_not_lookup_latest_date(self):
        from http.server import ThreadingHTTPServer
        from threading import Thread
        from urllib.request import urlopen
        from jev_demo.__main__ import handler_for, RunApplication
        with patch.dict('os.environ', {'JEV_DEMO_CACHE': str(self.directory)}):
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(
                RunApplication(self.store, lambda *_: None),
                lambda: self.fail('historical page must not fetch calendar')))
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f'http://127.0.0.1:{server.server_port}'
                with urlopen(base + f'/api/runs/{self.id}/visualization') as response:
                    self.assertEqual(self.id, json.load(response)['run_id'])
                with urlopen(base + f'/?run={self.id}') as response:
                    page = response.read().decode()
                self.assertIn('Show raw decision log', page)
                self.assertIn('/dashboard.js', page)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_rendered_dashboard_mobile_smoke(self):
        import subprocess
        from http.server import ThreadingHTTPServer
        from threading import Thread
        from urllib.request import urlopen
        from jev_demo.__main__ import handler_for, RunApplication
        browsers = list((Path.home() / '.cache/ms-playwright').glob('chromium_headless_shell-*/chrome-linux/headless_shell'))
        if not browsers:
            self.skipTest('Install Chromium or Playwright Chromium to run rendered smoke test')
        smoke = Path(__file__).with_name('dashboard_smoke.js').read_text()
        handler = handler_for(RunApplication(self.store, lambda *_: None), lambda: '2026-09-18')
        run_id = self.id
        class SmokeHandler(handler):
            def do_GET(self):
                if self.path != '/smoke':
                    return super().do_GET()
                with urlopen(f'http://127.0.0.1:{self.server.server_port}/?run={run_id}') as response:
                    page = response.read().decode()
                body = page.replace('</html>', '<script>' + smoke + '</script></html>').encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(body)
        with patch.dict('os.environ', {'JEV_DEMO_CACHE': str(self.directory)}):
            server = ThreadingHTTPServer(('127.0.0.1', 0), SmokeHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = subprocess.run([str(browsers[0]), '--headless', '--no-sandbox',
                    '--disable-gpu', '--no-proxy-server', '--window-size=375,900',
                    '--virtual-time-budget=15000', '--dump-dom',
                    f'http://127.0.0.1:{server.server_port}/smoke'], capture_output=True, text=True, timeout=40)
                self.assertEqual(0, result.returncode, result.stderr[-1000:])
                self.assertIn('data-smoke="passed"', result.stdout,
                              result.stdout[-5000:])
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
