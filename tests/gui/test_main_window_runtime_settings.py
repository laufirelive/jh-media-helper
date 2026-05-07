from src.core.app_settings import AppSettings
from src.core.config import CombatAudioConfig, TaskType
from src.gui import main_window
from src.gui.main_window import MainWindow


class _FakeSignal:
    def connect(self, *_args, **_kwargs):
        pass


class _FakeWorker:
    created = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.progress = _FakeSignal()
        self.finished = _FakeSignal()
        self.error = _FakeSignal()
        self.started = False
        _FakeWorker.created.append(self)

    def start(self):
        self.started = True


class _FakeCombatPanel:
    def __init__(self):
        self.observations = []
        self._mkvmerge_path = None
        self._mux_backend = "unset"

    def set_mux_settings(self, *, mkvmerge_path: str | None, mux_backend: str = "auto") -> None:
        self._mkvmerge_path = mkvmerge_path
        self._mux_backend = mux_backend
        self.observations.append(("set_mux_settings", mkvmerge_path, mux_backend))

    def validate(self):
        self.observations.append(("validate", self._mkvmerge_path, self._mux_backend))
        return True, 1, None

    def build_config(self):
        self.observations.append(("build_config", self._mkvmerge_path, self._mux_backend))
        return CombatAudioConfig(
            input_path="/tmp/input.mkv",
            audio_dir="/tmp/audio",
            mkvmerge_path=self._mkvmerge_path,
            mux_backend=self._mux_backend,
        )

    def get_task_type(self):
        return TaskType.COMBAT_AUDIO

    def on_progress(self, *_args):
        pass


class _NoopQueueTab:
    def __init__(self):
        self.refreshed = False

    def refresh(self):
        self.refreshed = True


class _FakeQueueManager:
    def __init__(self):
        self.tasks = []
        self.saved = False

    def add_task(self, task):
        self.tasks.append(task)

    def save(self):
        self.saved = True


def _make_window(monkeypatch, qapp):
    monkeypatch.setattr(MainWindow, "_check_queue_recovery", lambda self: None)
    monkeypatch.setattr(main_window.EncoderRegistry, "_probe", lambda self: None)
    monkeypatch.setattr(main_window.PreviewCacheSession, "start", lambda self: None)
    win = MainWindow()
    win._btn_start.setEnabled(True)
    win._btn_cancel.setEnabled(False)
    return win


def test_on_start_applies_saved_mux_settings_before_validate_and_build(qapp, monkeypatch):
    win = _make_window(monkeypatch, qapp)
    panel = _FakeCombatPanel()
    _FakeWorker.created.clear()

    monkeypatch.setattr(main_window, "CombatAudioPanel", _FakeCombatPanel)
    monkeypatch.setattr(main_window, "load_settings", lambda: AppSettings(mkvmerge_path="/opt/bin/mkvmerge"))
    monkeypatch.setattr(win, "_get_active_panel", lambda: panel)
    monkeypatch.setattr(main_window, "FFmpegWorker", _FakeWorker)

    win._on_start()

    assert panel.observations == [
        ("set_mux_settings", "/opt/bin/mkvmerge", "auto"),
        ("validate", "/opt/bin/mkvmerge", "auto"),
        ("build_config", "/opt/bin/mkvmerge", "auto"),
    ]
    assert _FakeWorker.created[0].kwargs["config"]["mkvmerge_path"] == "/opt/bin/mkvmerge"
    assert _FakeWorker.created[0].kwargs["config"]["mux_backend"] == "auto"
    assert _FakeWorker.created[0].started is True


def test_on_enqueue_applies_saved_mux_settings_before_validate_and_queues_config(qapp, monkeypatch):
    win = _make_window(monkeypatch, qapp)
    panel = _FakeCombatPanel()
    queue_manager = _FakeQueueManager()
    queue_tab = _NoopQueueTab()

    monkeypatch.setattr(main_window, "CombatAudioPanel", _FakeCombatPanel)
    monkeypatch.setattr(main_window, "load_settings", lambda: AppSettings(mkvmerge_path="/usr/local/bin/mkvmerge"))
    monkeypatch.setattr(win, "_get_active_panel", lambda: panel)
    monkeypatch.setattr(
        "src.core.processors.combat_audio.resolve_output_path",
        lambda config, audio_count: ["/tmp/output.mkv"],
    )
    win._queue_manager = queue_manager
    win._queue_tab = queue_tab

    win._on_enqueue()

    assert panel.observations == [
        ("set_mux_settings", "/usr/local/bin/mkvmerge", "auto"),
        ("validate", "/usr/local/bin/mkvmerge", "auto"),
        ("build_config", "/usr/local/bin/mkvmerge", "auto"),
    ]
    assert queue_manager.tasks[0].config["mkvmerge_path"] == "/usr/local/bin/mkvmerge"
    assert queue_manager.tasks[0].config["mux_backend"] == "auto"
    assert queue_manager.saved is True
    assert queue_tab.refreshed is True
