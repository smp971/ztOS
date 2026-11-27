# SPDX-License-Identifier: GPL-2.0-only
"""Note9 interfaces backed by its running Crown drivers and daemons."""
import os
from pathlib import Path
import re
import stat

from ztos_ial.backends import Backend, NotSupported, read, read_int
from ztos_ial.backends.generic import Haptics as GenericHaptics
from ztos_ial.backends.generic import Sleep as GenericSleep


class Sleep(GenericSleep):
    def available(self):
        return False

    def props(self):
        return {"Method": "unavailable", "Enabled": False, "State": "awake",
                "Inhibitors": sorted(f"{who}: {why}" for who, why, _ in self.held.values())}

    def m_SetEnabled(self, enabled):
        if enabled:
            raise NotSupported("suspend is not validated on crownlte")


class Haptics(GenericHaptics):
    """The input device can appear after IAL starts, when Crown's module loads."""
    def _refresh(self):
        self.device = self._find(self.config.get('device'))

    def available(self):
        self._refresh()
        return super().available()

    def props(self):
        self._refresh()
        return super().props()

    def m_Vibrate(self, milliseconds, strength):
        self._refresh()
        return super().m_Vibrate(milliseconds, strength)


MODEM_STATUS = '/run/ztoscorenetworking/status'
MODEM_CTL = '/run/ztoscorenetworking.ctl'
MODEM_STATE = '/sys/devices/platform/10000.mif_pdata/modem_state'
ABOX = '/sys/module/snd_crown_abox/parameters'
AUDIO_PCM = '/dev/snd/pcmC0D0p'


def modem_status():
    return dict(line.split('=', 1) for line in (read(MODEM_STATUS, '') or '').splitlines()
                if '=' in line)


def control_fd():
    """Never block the bus on a stopped daemon or write to a non-FIFO file."""
    try:
        fd = os.open(MODEM_CTL, os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError as error:
        raise NotSupported('Crown modem control is unavailable') from error
    if not stat.S_ISFIFO(os.fstat(fd).st_mode):
        os.close(fd)
        raise NotSupported('Crown modem control is not a FIFO')
    return fd


def tell(line):
    if any(c in line for c in '\r\n\0'):
        raise NotSupported('invalid modem command')
    data = (line + '\n').encode()
    fd = control_fd()
    try:
        if len(data) > os.fpathconf(fd, 'PC_PIPE_BUF'):
            raise NotSupported('modem command is too long')
        if os.write(fd, data) != len(data):
            raise NotSupported('incomplete modem command')
    except OSError as error:
        raise NotSupported('Crown modem control did not accept the command') from error
    finally:
        os.close(fd)


def phone_number(number):
    if not re.fullmatch(r'\+?[0-9*#]{1,30}', number):
        raise NotSupported('invalid phone number')
    return number


class Modem(Backend):
    """Shannon status and the same control protocol used by the native apps.

    A connected data context is not proof of Internet access or a data plan.
    Voice routing is deliberately kept separate in CallAudio1.
    """
    interface = 'Modem1'
    poll_s = 5

    def available(self):
        if not Path(MODEM_STATE).exists() or not modem_status():
            return False
        try:
            os.close(control_fd())
            return True
        except NotSupported:
            return False

    def props(self):
        s = modem_status()
        online = read(MODEM_STATE, '') == 'ONLINE' and self.available()
        try:
            signal = max(0, min(5, int(s.get('bars', '0')))) * 20
        except ValueError:
            signal = 0
        powered = online and s.get('airplane', '1') == '0'
        return {
            'Present': Path(MODEM_STATE).exists(),
            'Powered': powered,
            'SimState': s.get('sim', 'unknown') if online else 'unknown',
            'Operator': s.get('operator', '') if online else '',
            'Signal': signal if powered else 0,
            'Technology': s.get('tech', '') if powered else '',
            'Registration': s.get('registered', 'none') if powered else 'none',
            'DataEnabled': s.get('data_on', '0') == '1',
            'DataConnected': powered and s.get('data', '0') == '1',
            'CallState': s.get('call', 'idle') if online else 'unknown',
            'CallNumber': s.get('call_number', '') if online else '',
        }

    def m_SetPowered(self, powered):
        tell('airplane off' if powered else 'airplane on')

    def m_SetDataEnabled(self, enabled):
        tell('data on' if enabled else 'data off')

    def m_Dial(self, number):
        tell('call ' + phone_number(number))

    def m_Answer(self):
        tell('answer')

    def m_Hangup(self):
        tell('hangup')

    def m_SendSms(self, number, text):
        number = phone_number(number)
        if '\0' in text or len(text.encode()) > 1800:
            raise NotSupported('SMS text is invalid or too long')
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        escaped = text.replace('\\', '\\\\').replace('\n', '\\n').replace('\t', '\\t')
        tell(f'smse {number} {escaped}')


class AudioDevice(Backend):
    """Read-only media-driver diagnostics; no unverified call/DSM activation."""
    interface = 'AudioDevice1'
    poll_s = 10

    def available(self):
        return Path(ABOX).is_dir() and Path(AUDIO_PCM).exists()

    def props(self):
        details = {'driver': 'snd_crown_abox', 'health_scope': 'driver recovery and codec counters',
                   'call_audio': 'unvalidated; CP VSS disabled',
                   'speaker_protection': 'not verified active'}
        for name in ('capture', 'cp_vss', 'pm_ready', 'fast_rebuilds', 'mixp_flushes',
                     'dsp_restarts', 'watchdog_recoveries', 'ipc_retries', 'codec_errors',
                     'pointer_stalls', 'pointer_backsteps'):
            value = read(Path(ABOX) / name)
            if value is not None:
                details[name] = value
        rdc = (read(Path(ABOX) / 'dsm_rdc', '') or '').split(',')
        try:
            calibrated = len(rdc) == 2 and all(int(x) > 0 for x in rdc) \
                and read_int(Path(ABOX) / 'dsm_temp') > 0
        except ValueError:
            calibrated = False
        healthy = self.available() and all(read_int(Path(ABOX) / name, -1) == 0
                  for name in ('watchdog_recoveries', 'codec_errors', 'dsp_restarts'))
        return {'SpeakerProtection': False, 'Calibrated': calibrated,
                'AmpHealthy': healthy, 'Details': details}
