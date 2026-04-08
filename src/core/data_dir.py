import os

_DEFAULT_DATA_DIR = os.path.join(os.path.expanduser("~"), ".jh-media-helper")

def resolve_data_dir() -> str:
    return _DEFAULT_DATA_DIR

def get_queue_path() -> str:
    return os.path.join(resolve_data_dir(), "queue.json")

def get_settings_path() -> str:
    return os.path.join(resolve_data_dir(), "settings.json")
