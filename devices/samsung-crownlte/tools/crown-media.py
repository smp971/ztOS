#!/usr/bin/python3
"""Local music and voice recordings; PipeWire audio, no network services."""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import sys
import tempfile
import time

from PySide6.QtCore import QProcess, QTimer, Qt
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QSlider, QFileDialog, QMessageBox)

FORMATS = {'.mp3', '.flac', '.ogg', '.opus', '.wav', '.m4a', '.aac', '.webm'}


def haptic():
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if not runtime:
        return
    try:
        fd = os.open(str(Path(runtime) / 'ztmetro.ctl'), os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            os.write(fd, b'haptic tap apps\n')
        finally:
            os.close(fd)
    except OSError:
        pass


class Media(QWidget):
    def __init__(self, recorder=False):
        super().__init__()
        self.recorder = recorder
        self.setWindowTitle('Voice Recorder' if recorder else 'Local Music')
        self.resize(360, 720)
        self.home = Path.home()
        self.folder = self.home / ('Documents/Recordings' if recorder else 'Music')
        self.folder.mkdir(parents=True, exist_ok=True)
        self.state = self.home / '.local/share/crown-media/playlist.json'
        self.extra = []
        if not recorder:
            try:
                saved = json.loads(self.state.read_text())
                if isinstance(saved, list):
                    self.extra = [Path(p) for p in saved if isinstance(p, str)]
            except (OSError, ValueError):
                pass
        self.tmp = tempfile.TemporaryDirectory(prefix='crown-media-',
            dir=os.environ.get('XDG_RUNTIME_DIR'))
        self.ipc = str(Path(self.tmp.name) / 'mpv.sock')
        self.player = QProcess(self)
        self.player.finished.connect(self.play_finished)
        self.player.errorOccurred.connect(lambda _: self.status.setText('Playback could not start.'))
        self.capture = QProcess(self)
        self.capture.finished.connect(self.record_finished)
        self.capture.errorOccurred.connect(self.record_error)
        self.capture_timeout = QTimer(self)
        self.capture_timeout.setSingleShot(True)
        self.capture_timeout.timeout.connect(self.capture.kill)
        self.recording = None
        self.stopping = False
        self.closing = False
        self.queue_next = False
        self.current = -1
        self.paused = False
        self.files = []
        layout = QVBoxLayout(self)
        title = QLabel('voice recorder' if recorder else 'local music')
        title.setStyleSheet('font-size:32px; font-weight:300;')
        layout.addWidget(title)
        self.status = QLabel('Saved in Documents/Recordings' if recorder else 'Music from your phone')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        if recorder:
            row = QHBoxLayout()
            self.record = QPushButton('● Record')
            self.record.clicked.connect(self.start_record)
            self.stop = QPushButton('■ Save')
            self.stop.setEnabled(False)
            self.stop.clicked.connect(self.stop_record)
            row.addWidget(self.record); row.addWidget(self.stop)
            layout.addLayout(row)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self.play())
        layout.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, action in [('‹', lambda: self.step(-1)), ('Play / pause', self.play_pause),
                             ('›', lambda: self.step(1))]:
            b = QPushButton(text); b.clicked.connect(action); row.addWidget(b)
        layout.addLayout(row)
        row = QHBoxLayout()
        for text, action in [('−10 sec', lambda: self.command('seek', -10, 'relative')),
                             ('+10 sec', lambda: self.command('seek', 10, 'relative'))]:
            b = QPushButton(text); b.clicked.connect(action); row.addWidget(b)
        layout.addLayout(row)
        layout.addWidget(QLabel('Volume'))
        self.volume = QSlider(Qt.Horizontal); self.volume.setRange(0, 100); self.volume.setValue(50)
        self.volume.valueChanged.connect(lambda v: self.command('set_property', 'volume', v))
        layout.addWidget(self.volume)
        row = QHBoxLayout()
        refresh = QPushButton('Refresh'); refresh.clicked.connect(self.refresh); row.addWidget(refresh)
        if not recorder:
            add = QPushButton('Add files'); add.clicked.connect(self.add_files); row.addWidget(add)
        else:
            delete = QPushButton('Delete selected'); delete.clicked.connect(self.delete); row.addWidget(delete)
        layout.addLayout(row)
        self.tick = QTimer(self); self.tick.timeout.connect(self.record_tick); self.tick.start(500)
        self.refresh()
        for button in self.findChildren(QPushButton):
            button.clicked.connect(haptic)
        self.volume.sliderReleased.connect(haptic)

    def refresh(self):
        selected = self.files[self.list.currentRow()] if 0 <= self.list.currentRow() < len(self.files) else None
        files = set(self.extra)
        for p in self.folder.rglob('*'):
            if p.suffix.lower() in FORMATS and p.is_file():
                files.add(p)
            if len(files) >= 2000:
                break
        self.files = sorted((p for p in files if p.is_file() and p.suffix.lower() in FORMATS),
                            key=lambda p: p.name.casefold())
        self.list.clear()
        self.list.addItems([p.stem for p in self.files])
        if selected in self.files:
            self.list.setCurrentRow(self.files.index(selected))
        elif self.files:
            self.list.setCurrentRow(0)

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Add music', str(self.folder),
            'Audio (*.mp3 *.flac *.ogg *.opus *.wav *.m4a *.aac *.webm)')
        self.extra = list(dict.fromkeys(self.extra + [Path(p) for p in paths]))
        self.state.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state.with_suffix('.tmp')
        temp.write_text(json.dumps([str(p) for p in self.extra]))
        temp.replace(self.state)
        self.refresh()

    def command(self, *args):
        try:
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(.1); s.connect(self.ipc)
                s.sendall((json.dumps({'command': args}) + '\n').encode())
            return True
        except OSError:
            return False

    def halt_player(self):
        self.queue_next = False
        if self.player.state() != QProcess.NotRunning:
            self.player.terminate()
            if not self.player.waitForFinished(1000):
                self.player.kill(); self.player.waitForFinished(500)

    def play(self):
        i = self.list.currentRow()
        if i < 0 or self.recording:
            return
        self.halt_player()
        self.current = i
        self.paused = False
        self.status.setText(self.files[i].name)
        self.queue_next = not self.recorder
        self.player.start('mpv', ['--no-config', '--no-video', '--ao=pipewire,pulse',
            '--input-ipc-server=' + self.ipc, '--volume=' + str(self.volume.value()),
            '--', str(self.files[i])])

    def play_pause(self):
        if self.player.state() == QProcess.NotRunning or self.current != self.list.currentRow():
            self.play()
        elif self.command('cycle', 'pause'):
            self.paused = not self.paused
            self.status.setText(('Paused: ' if self.paused else '') + self.files[self.current].name)

    def step(self, delta):
        if self.files:
            i = self.list.currentRow()
            self.list.setCurrentRow((i + delta) % len(self.files))
            self.play()

    def play_finished(self, code, status):
        if self.queue_next and not self.closing and code == 0 and status == QProcess.NormalExit:
            self.queue_next = False
            if self.current + 1 < len(self.files):
                self.list.setCurrentRow(self.current + 1)
                QTimer.singleShot(0, self.play)

    def start_record(self):
        if self.recording:
            return
        if shutil.disk_usage(self.folder).free < 100 * 1024 * 1024:
            self.status.setText('Not enough free storage (100 MB needed).'); return
        self.halt_player()
        # Exclusive creation avoids overwriting an earlier recording.
        import datetime
        name = datetime.datetime.now().strftime('Recording %Y-%m-%d %H-%M-%S-%f.wav')
        self.recording = self.folder / name
        fd = os.open(self.recording, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600); os.close(fd)
        self.started = time.monotonic(); self.stopping = False
        self.record.setEnabled(False); self.stop.setEnabled(True)
        self.status.setText('Recording… 0:00')
        self.capture.start('pw-record', ['--target=crown-microphone', '--rate=48000',
            '--channels=2', str(self.recording)])

    def stop_record(self):
        if self.recording and not self.stopping:
            self.stopping = True
            self.stop.setEnabled(False)
            pid = self.capture.processId()
            if pid:
                try:
                    os.kill(pid, signal.SIGINT)  # finalize the WAV header
                except ProcessLookupError:
                    pass
            self.capture_timeout.start(3000)

    def record_tick(self):
        if self.recording and not self.stopping:
            elapsed = int(time.monotonic() - self.started)
            self.status.setText(f'Recording… {elapsed // 60}:{elapsed % 60:02d}')
            if elapsed >= 3600 or shutil.disk_usage(self.folder).free < 20 * 1024 * 1024:
                self.stop_record()

    def record_error(self, error):
        if error == QProcess.FailedToStart:
            self.record_finished(1, QProcess.CrashExit)

    def record_finished(self, code, status):
        self.capture_timeout.stop()
        path = self.recording
        self.recording = None; self.stopping = False
        self.record.setEnabled(True); self.stop.setEnabled(False)
        if path and path.exists() and path.stat().st_size > 44 and code == 0:
            self.status.setText('Saved: ' + path.name)
        else:
            self.status.setText('Recording failed. Check the microphone and storage.')
            if path and path.exists() and path.stat().st_size <= 44:
                path.unlink()
        self.refresh()
        if path in self.files:
            self.list.setCurrentRow(self.files.index(path))

    def delete(self):
        i = self.list.currentRow()
        if i < 0 or self.recording:
            return
        path = self.files[i]
        if QMessageBox.question(self, 'Delete recording', 'Delete ' + path.name + '?') == QMessageBox.Yes:
            self.halt_player()
            try:
                path.unlink(); self.refresh()
            except OSError as e:
                self.status.setText(str(e))

    def closeEvent(self, event):
        self.closing = True
        if self.recording:
            self.stop_record()
            if not self.capture.waitForFinished(3000):
                self.capture.kill(); self.capture.waitForFinished(500)
        self.halt_player(); self.tmp.cleanup(); event.accept()


if __name__ == '__main__':
    os.umask(0o077)
    app = QApplication(sys.argv)
    recorder = '--recorder' in sys.argv
    app.setDesktopFileName('com.zerone.recorder' if recorder else 'com.zerone.localmusic')
    app.setStyleSheet('QWidget {background:#101010;color:white;font-size:18px;} '
        'QPushButton {background:#242424;border:1px solid #555;padding:12px;} '
        'QPushButton:pressed {background:#007aaf;} QPushButton:disabled {color:#777;} '
        'QListWidget {border:0;} QListWidget::item {padding:14px;} '
        'QListWidget::item:selected {background:#006995;} QSlider {min-height:36px;}')
    win = Media(recorder); win.show(); sys.exit(app.exec())
