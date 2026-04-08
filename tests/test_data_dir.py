import os
from src.core.data_dir import get_queue_path, get_settings_path, resolve_data_dir

def test_resolve_data_dir_default():
    result = resolve_data_dir()
    expected = os.path.join(os.path.expanduser("~"), ".jh-media-helper")
    assert result == expected

def test_get_queue_path():
    path = get_queue_path()
    assert path.endswith("queue.json")

def test_get_settings_path():
    path = get_settings_path()
    assert path.endswith("settings.json")
