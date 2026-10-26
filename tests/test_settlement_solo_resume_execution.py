"""Signed resume boundary regressions; disposable mocks, never live authority."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import settlement_financial_maintenance as m


class SoloResumeBoundaryTests(unittest.TestCase):
    def test_legacy_fence_without_pre_hold_identity_seal_can_never_resume(self):
        with patch.object(m, 'private_json', return_value=({'schema':m.FENCE_SCHEMA},'a'*64)), \
             patch.object(m, 'run') as command:
            with self.assertRaisesRegex(m.MaintenanceError, 'RESUME_CAPTURE_IDENTITIES_MISSING'):
                m.verify_resume_state(Path('/root/fence'), Path('/root/backup'),
                                      Path('/root/backup/restore.json'), {}, runner=command)
            command.assert_not_called()

    def test_resume_requires_a_fresh_separate_phase_before_systemd_or_hold_changes(self):
        for phase in ('live_capture','offline_verify','funded_activate',None):
            with self.subTest(phase=phase), patch.object(m,'run') as command:
                with self.assertRaisesRegex(m.MaintenanceError, 'RESUME_PHASE_ONLY'):
                    m.resume_existing(Path('/root/fence'), Path('/root/backup'),
                                      phase_window={'phase':phase},runner=command)
                command.assert_not_called()


if __name__=='__main__':
    unittest.main()
