"""Crown IAL protocol tests. All device nodes and the modem FIFO are temporary.

Run on Linux: python3 devices/samsung-crownlte/tests/test_ial.py
An on-phone staged module can be selected with CROWN_IAL_MODULE.
"""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'ial'))
module_path = Path(os.environ.get('CROWN_IAL_MODULE') or
                   Path(__file__).resolve().parents[1] / 'vendor/ztos/ial/crownlte.py')
spec = importlib.util.spec_from_file_location('crown_ial', module_path)
crown = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crown)


class HapticsTests(unittest.TestCase):
    def test_input_device_can_appear_after_daemon_start(self):
        with patch.object(crown.Haptics, '_find', return_value='') as find:
            haptic = crown.Haptics({'device': 'zrn-haptic'}, {})
            self.assertFalse(haptic.available())
            find.return_value = '/dev/input/event2'
            self.assertTrue(haptic.available())
            self.assertEqual(haptic.props()['Device'], '/dev/input/event2')
            find.return_value = ''
            self.assertFalse(haptic.available())


@unittest.skipUnless(hasattr(os, 'mkfifo'), 'requires Linux FIFOs')
class ModemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.status, self.state, self.ctl = [self.root / n for n in ('status', 'state', 'control')]
        self.state.write_text('ONLINE\n')
        self.status.write_text('sim=ready\nairplane=0\nbars=2\nregistered=home\n'
                               'tech=4G\ndata_on=1\ndata=1\ncall=idle\n')
        os.mkfifo(self.ctl)
        self.reader = os.open(self.ctl, os.O_RDONLY | os.O_NONBLOCK)
        self.addCleanup(self.close_reader)
        p = patch.multiple(crown, MODEM_STATUS=str(self.status), MODEM_STATE=str(self.state),
                           MODEM_CTL=str(self.ctl))
        p.start()
        self.addCleanup(p.stop)
        self.modem = crown.Modem({}, {})

    def close_reader(self):
        if self.reader is not None:
            os.close(self.reader)
            self.reader = None

    def test_live_mapping_and_five_bar_scale(self):
        p = self.modem.props()
        self.assertTrue(self.modem.available())
        self.assertTrue(p['Powered'])
        self.assertEqual((p['SimState'], p['Signal'], p['Technology']), ('ready', 40, '4G'))
        self.status.write_text(self.status.read_text().replace('bars=2', 'bars=5'))
        self.assertEqual(self.modem.props()['Signal'], 100)

    def test_dead_daemon_does_not_reuse_stale_connected_state(self):
        self.close_reader()
        self.assertFalse(self.modem.available())
        p = self.modem.props()
        self.assertFalse(p['Powered'])
        self.assertFalse(p['DataConnected'])
        self.assertEqual(p['SimState'], 'unknown')
        with self.assertRaises(crown.NotSupported):
            self.modem.m_SetDataEnabled(True)

    def test_offline_cp_and_airplane_mode(self):
        self.state.write_text('OFFLINE')
        self.assertFalse(self.modem.props()['DataConnected'])
        self.state.write_text('ONLINE')
        self.status.write_text(self.status.read_text().replace('airplane=0', 'airplane=1'))
        self.assertFalse(self.modem.props()['Powered'])
        self.assertEqual(self.modem.props()['Registration'], 'none')

    def test_control_protocol_uses_only_temporary_fifo(self):
        self.modem.m_SetPowered(True)
        self.modem.m_SetDataEnabled(False)
        self.assertEqual(os.read(self.reader, 4096), b'airplane off\ndata off\n')
        self.modem.m_SendSms('000', 'one\ntwo\\three\tfour')
        self.assertEqual(os.read(self.reader, 4096), b'smse 000 one\\ntwo\\\\three\\tfour\n')

    def test_rejects_command_injection_and_oversized_text(self):
        for number in ('', '000\nhangup', '000;AT', '0' * 32):
            with self.assertRaises(crown.NotSupported):
                self.modem.m_Dial(number)
        for text in ('bad\0text', 'x' * 1801):
            with self.assertRaises(crown.NotSupported):
                self.modem.m_SendSms('000', text)
        with self.assertRaises(crown.NotSupported):
            crown.tell('data off\nairplane on')

    def test_non_fifo_is_never_written(self):
        self.close_reader()
        self.ctl.unlink()
        self.ctl.write_text('untouched')
        with self.assertRaises(crown.NotSupported):
            self.modem.m_SetPowered(False)
        self.assertEqual(self.ctl.read_text(), 'untouched')


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pcm = self.root / 'pcm'
        self.pcm.touch()
        for n in ('watchdog_recoveries', 'codec_errors', 'dsp_restarts'):
            (self.root / n).write_text('0')
        p = patch.multiple(crown, ABOX=str(self.root), AUDIO_PCM=str(self.pcm))
        p.start()
        self.addCleanup(p.stop)
        self.audio = crown.AudioDevice({}, {})

    def test_fault_counters_and_missing_device(self):
        self.assertTrue(self.audio.props()['AmpHealthy'])
        (self.root / 'watchdog_recoveries').write_text('1')
        self.assertFalse(self.audio.props()['AmpHealthy'])
        self.pcm.unlink()
        self.assertFalse(self.audio.available())

    def test_calibration_is_not_claimed_as_active_protection(self):
        self.assertFalse(self.audio.props()['Calibrated'])
        (self.root / 'dsm_rdc').write_text('100,200')
        (self.root / 'dsm_temp').write_text('250')
        self.assertTrue(self.audio.props()['Calibrated'])
        self.assertFalse(self.audio.props()['SpeakerProtection'])


if __name__ == '__main__':
    unittest.main()
