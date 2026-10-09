import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import requests
import health_check as hc


class HealthCheckTests(unittest.TestCase):
    def tearDown(self):
        for handler in hc.LOGGER.handlers[:]:
            handler.close()
            hc.LOGGER.removeHandler(handler)

    def test_threshold_boundaries(self):
        for value, expected in [(69.9, 'HEALTHY'), (70, 'WARNING'),
                                (89.9, 'WARNING'), (90, 'CRITICAL'), (100, 'CRITICAL')]:
            with self.subTest(value=value):
                self.assertEqual(hc.get_status(value, 70, 90), expected)

    def test_incident_contract_and_healthy_suppression(self):
        self.assertEqual(hc.evaluate_metric('host', 'cpu', 20, 70, 90), ('HEALTHY', None))
        for value, severity, threshold in [(70, 'warning', 70), (95, 'critical', 90)]:
            _, incident = hc.evaluate_metric('host', 'cpu', value, 70, 90)
            self.assertEqual(incident, dict(hostname='host', metric='cpu', value=value,
                                            threshold=threshold, severity=severity))

    def test_invalid_thresholds(self):
        for values in [('90', '70'), ('70', '70'), ('-1', '90'), ('70', '101'),
                       ('nan', '90'), ('70', 'inf')]:
            with self.subTest(values=values), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    hc.parse_args(['--cpu-warning', values[0], '--cpu-critical', values[1]])

    def test_report_collection(self):
        with patch.object(hc.psutil, 'cpu_percent', return_value=70), \
             patch.object(hc.psutil, 'virtual_memory', return_value=SimpleNamespace(
                 percent=20, total=1000, used=200, available=800)), \
             patch.object(hc.shutil, 'disk_usage', return_value=SimpleNamespace(
                 total=1000, used=950, free=50)) as disk, \
             patch.object(hc.psutil, 'boot_time', return_value=100), \
             patch.object(hc.time, 'time', return_value=3700):
            report = hc.collect_report(hc.DEFAULT_THRESHOLDS, '/data')
        self.assertEqual(report['status'], 'CRITICAL')
        self.assertEqual(report['uptime_seconds'], 3600)
        self.assertEqual(len(report['incidents']), 2)
        self.assertEqual(report['metrics']['memory']['available_bytes'], 800)
        self.assertTrue(report['timestamp'].endswith('+01:00'))
        disk.assert_called_once_with('/data')

    def report(self, status='WARNING'):
        return {'status': status, 'incidents': [hc.create_incident('host', 'cpu', 75, 70, 'WARNING')]}

    def test_json_and_exit_codes_no_webhook(self):
        for status, code in hc.EXIT_CODES.items():
            out, err = io.StringIO(), io.StringIO()
            with patch.object(hc, 'collect_report', return_value=self.report(status)), \
                 patch.object(hc, 'send_incident') as send, \
                 patch.dict(os.environ, {'N8N_WEBHOOK_URL': 'https://example.invalid/private'}), \
                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(hc.main(['--format', 'json', '--no-webhook']), code)
            self.assertEqual(json.loads(out.getvalue())['status'], status)
            self.assertIn('+01:00', err.getvalue())
            send.assert_not_called()

    def test_collection_error(self):
        with patch.object(hc, 'collect_report', side_effect=FileNotFoundError), \
             contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(hc.main(['--no-webhook']), 3)
        self.assertEqual(out.getvalue(), '')

    def test_webhook_success_timeout_and_http_error(self):
        incident = self.report()['incidents'][0]
        with patch.dict(os.environ, {'N8N_WEBHOOK_URL': 'https://example.invalid/private'}), \
             patch.object(hc.requests, 'post') as post:
            self.assertTrue(hc.send_incident(incident))
            post.assert_called_once_with('https://example.invalid/private', json=incident, timeout=5)
            for failure in [requests.Timeout('secret-url'), requests.HTTPError('secret-url')]:
                post.side_effect = failure
                with self.assertLogs(hc.LOGGER, level='ERROR') as logs:
                    self.assertFalse(hc.send_incident(incident))
                self.assertNotIn('secret-url', ' '.join(logs.output))

    def test_missing_webhook_does_not_post(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(hc.requests, 'post') as post:
            self.assertFalse(hc.send_incident(self.report()['incidents'][0]))
        post.assert_not_called()

    def test_delivery_failure_exit(self):
        with patch.object(hc, 'collect_report', return_value=self.report()), \
             patch.object(hc, 'send_incident', return_value=False), \
             patch.dict(os.environ, {'N8N_WEBHOOK_URL': 'https://example.invalid/private'}), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(hc.main(['--format', 'json']), 3)

    def test_optional_log_file(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            path = Path(directory) / 'health.log'
            hc.configure_logging(str(path))
            hc.LOGGER.info('test event')
            self.assertIn('test event', path.read_text())
            self.assertIn('+01:00', path.read_text())
            self.assertTrue(any(isinstance(h, hc.RotatingFileHandler) for h in hc.LOGGER.handlers))


if __name__ == '__main__':
    unittest.main()
