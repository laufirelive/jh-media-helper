import importlib
import sys
import types
from unittest.mock import Mock, patch


def _install_pyqt_stubs():
    pyqt6 = types.ModuleType("PyQt6")
    qtwidgets = types.ModuleType("PyQt6.QtWidgets")

    class QApplication:
        def __init__(self, *args, **kwargs):
            pass

    class QMessageBox:
        @staticmethod
        def critical(*args, **kwargs):
            pass

    qtwidgets.QApplication = QApplication
    qtwidgets.QMessageBox = QMessageBox
    pyqt6.QtWidgets = qtwidgets

    sys.modules["PyQt6"] = pyqt6
    sys.modules["PyQt6.QtWidgets"] = qtwidgets


def _load_main_module():
    _install_pyqt_stubs()
    sys.modules.pop("main", None)
    return importlib.import_module("main")

def test_main_shows_dialog_and_exits_when_ffmpeg_tools_missing():
    with patch.dict(
        sys.modules,
        {"src.gui.main_window": types.SimpleNamespace(MainWindow=Mock())},
        clear=False,
    ):
        main = _load_main_module()
    app = Mock()

    with patch.object(main.multiprocessing, "freeze_support") as mock_freeze_support, \
         patch.object(main, "QApplication", return_value=app) as mock_app_cls, \
         patch.object(main, "has_required_ffmpeg_tools", return_value=False) as mock_has_tools, \
         patch.object(main.QMessageBox, "critical") as mock_critical, \
         patch.object(main.sys, "exit") as mock_exit:
        main.main()

    mock_freeze_support.assert_called_once_with()
    mock_app_cls.assert_called_once()
    mock_has_tools.assert_called_once_with()
    mock_critical.assert_called_once()
    mock_exit.assert_called_once_with(1)


def test_main_starts_window_when_ffmpeg_tools_exist():
    window_stub = Mock()
    with patch.dict(
        sys.modules,
        {"src.gui.main_window": types.SimpleNamespace(MainWindow=Mock())},
        clear=False,
    ):
        main = _load_main_module()
    app = Mock()
    app.exec.return_value = 0

    with patch.object(main.multiprocessing, "freeze_support") as mock_freeze_support, \
         patch.object(main, "QApplication", return_value=app) as mock_app_cls, \
         patch.object(main, "has_required_ffmpeg_tools", return_value=True) as mock_has_tools, \
         patch.object(main, "MainWindow", return_value=window_stub) as mock_window_cls, \
         patch.object(main.sys, "exit") as mock_exit:
        main.main()

    mock_freeze_support.assert_called_once_with()
    mock_app_cls.assert_called_once()
    mock_has_tools.assert_called_once_with()
    mock_window_cls.assert_called_once_with()
    window_stub.show.assert_called_once_with()
    mock_exit.assert_called_once_with(0)
