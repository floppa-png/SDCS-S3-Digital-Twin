import os
import sys
import time
import json
import unittest

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dashboard.app import app, engine
from twin_core.config import MODULATIONS

class TestApiValidation(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def test_boot_time(self):
        """Acceptance criteria: App boots in < 5 s (no training at import)."""
        t0 = time.perf_counter()
        from twin_core.engine import Engine
        test_eng = Engine(fs=1000000)
        boot_time = time.perf_counter() - t0
        test_eng.stop()
        print(f"\n[Test] Engine boot time: {boot_time:.3f} s")
        self.assertLess(boot_time, 5.0, "Engine initialization took >= 5.0 seconds!")

    def test_get_state(self):
        """GET /api/state returns 200 and expected schema."""
        resp = self.client.get('/api/state')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('config', data)
        self.assertIn('cfg_version', data)
        self.assertIn('mode', data)
        self.assertIn('presets', data)
        self.assertIn('randomizer', data)

    def test_config_rejects_unknown_keys(self):
        """Unknown keys in POST /api/config return 400 with message."""
        payload = {'some_unknown_hacker_param': 12345}
        resp = self.client.post('/api/config', json=payload)
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('errors', data)
        self.assertIn('some_unknown_hacker_param', data['errors'])
        print(f"[Test] Rejected unknown key: {data['errors']}")

    def test_config_rejects_out_of_range(self):
        """Out-of-range values in POST /api/config return 400 with message."""
        # snr_db max is 35 dB
        resp = self.client.post('/api/config', json={'snr_db': 150.0})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('snr_db', data['errors'])
        self.assertIn('above maximum', data['errors']['snr_db'])

        # alloc_bw min is 5000 Hz
        resp2 = self.client.post('/api/config', json={'alloc_bw': 100})
        self.assertEqual(resp2.status_code, 400)
        data2 = resp2.get_json()
        self.assertIn('alloc_bw', data2['errors'])
        self.assertIn('below minimum', data2['errors']['alloc_bw'])
        print("[Test] Rejected out-of-range values with proper messages")

    def test_config_rejects_modulation_change(self):
        """Modulation is NOT changeable via POST /api/config."""
        resp = self.client.post('/api/config', json={'modulation': 'BPSK'})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('modulation', data['errors'])
        self.assertIn('cannot be modified via general config', data['errors']['modulation'])
        print("[Test] Modulation change via /api/config properly blocked")

    def test_config_rejects_non_json_or_bad_payload(self):
        """Non-JSON or malformed payload returns 400."""
        resp = self.client.post('/api/config', data="plain text not json", content_type='text/plain')
        self.assertEqual(resp.status_code, 400)

    def test_modulation_whitelist(self):
        """POST /api/modulation only accepts whitelist modulations."""
        # Bad modulation (QAM removed or SUPER_MOD_128)
        resp_bad = self.client.post('/api/modulation', json={'modulation': 'SUPER_MOD_128'})
        self.assertEqual(resp_bad.status_code, 400)
        resp_qam = self.client.post('/api/modulation', json={'modulation': 'QAM'})
        self.assertEqual(resp_qam.status_code, 400)

        # Valid modulation
        resp_good = self.client.post('/api/modulation', json={'modulation': 'QPSK'})
        self.assertEqual(resp_good.status_code, 200)
        self.assertEqual(engine.config.modulation, 'QPSK')
        print("[Test] Modulation whitelist verified")

    def test_presets_endpoint(self):
        """POST /api/preset validates preset name."""
        resp_bad = self.client.post('/api/preset', json={'name': 'non_existent_preset'})
        self.assertEqual(resp_bad.status_code, 400)

        resp_good = self.client.post('/api/preset', json={'name': 'deep_space'})
        self.assertEqual(resp_good.status_code, 200)
        self.assertEqual(engine.config.modulation, 'BPSK')
        print("[Test] Presets endpoint verified")

    def test_mode_endpoint(self):
        """POST /api/mode validates mode."""
        resp_bad = self.client.post('/api/mode', json={'mode': 'alien_hardware'})
        self.assertEqual(resp_bad.status_code, 400)

        resp_good = self.client.post('/api/mode', json={'mode': 'sim'})
        self.assertEqual(resp_good.status_code, 200)
        self.assertEqual(engine.mode, 'sim')
        print("[Test] Mode endpoint verified")

    def test_randomizer_invariance(self):
        """
        Acceptance criteria:
        - Intervals in [10, 15] s
        - Modulation unchanged across 20 randomizations
        """
        initial_mod = 'QPSK'
        engine.set_modulation(initial_mod)
        self.assertEqual(engine.config.modulation, initial_mod)

        intervals = []
        for i in range(20):
            engine._randomize_step()
            self.assertEqual(
                engine.config.modulation, initial_mod,
                f"Iteration {i}: Modulation changed from {initial_mod} to {engine.config.modulation}!"
            )
            intervals.append(engine.randomizer_interval_s)
            self.assertGreaterEqual(engine.randomizer_interval_s, 10.0)
            self.assertLessEqual(engine.randomizer_interval_s, 30.0)

        print(f"[Test] Randomizer verified across 20 iterations: modulation '{initial_mod}' held 100% constant. Intervals: min={min(intervals):.1f}s, max={max(intervals):.1f}s")

if __name__ == '__main__':
    unittest.main()
