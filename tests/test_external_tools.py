import os

from src.core.external_tools import MuxBackend, resolve_mkvmerge_path, resolve_mux_backend


def test_resolve_mkvmerge_path_prefers_valid_manual_path(monkeypatch, tmp_path):
    tool = tmp_path / "mkvmerge"
    tool.write_text("#!/bin/sh\n", encoding="utf-8")
    tool.chmod(0o755)
    monkeypatch.setattr("src.core.external_tools.shutil.which", lambda name: None)

    assert resolve_mkvmerge_path(str(tool)) == str(tool)


def test_resolve_mkvmerge_path_falls_back_to_path_when_manual_invalid(monkeypatch, tmp_path):
    tool = tmp_path / "mkvmerge"
    tool.write_text("#!/bin/sh\n", encoding="utf-8")
    tool.chmod(0o755)
    monkeypatch.setattr("src.core.external_tools.shutil.which", lambda name: str(tool))

    assert resolve_mkvmerge_path("/missing/mkvmerge") == str(tool)


def test_resolve_mkvmerge_path_returns_none_when_not_found(monkeypatch):
    monkeypatch.setattr("src.core.external_tools.shutil.which", lambda name: None)

    assert resolve_mkvmerge_path(None) is None


def test_resolve_mkvmerge_path_ignores_non_executable_path_result(monkeypatch, tmp_path):
    tool = tmp_path / "mkvmerge"
    tool.write_text("", encoding="utf-8")
    tool.chmod(0o644)
    monkeypatch.setattr("src.core.external_tools.shutil.which", lambda name: str(tool))

    assert resolve_mkvmerge_path(None) is None


def test_resolve_mux_backend_uses_mkvmerge_when_available(monkeypatch):
    monkeypatch.setattr("src.core.external_tools.resolve_mkvmerge_path", lambda path: "/usr/bin/mkvmerge")

    backend, path = resolve_mux_backend("auto", None)

    assert backend == MuxBackend.MKVMERGE
    assert path == "/usr/bin/mkvmerge"


def test_resolve_mux_backend_falls_back_to_ffmpeg(monkeypatch):
    monkeypatch.setattr("src.core.external_tools.resolve_mkvmerge_path", lambda path: None)

    backend, path = resolve_mux_backend("auto", None)

    assert backend == MuxBackend.FFMPEG
    assert path is None


def test_manual_path_must_be_executable(tmp_path, monkeypatch):
    tool = tmp_path / "mkvmerge"
    tool.write_text("", encoding="utf-8")
    tool.chmod(0o644)
    monkeypatch.setattr("src.core.external_tools.shutil.which", lambda name: None)

    assert resolve_mkvmerge_path(str(tool)) is None


def test_manual_path_must_not_be_empty(tmp_path, monkeypatch):
    tool = tmp_path / "mkvmerge"
    tool.touch()
    tool.chmod(0o755)
    monkeypatch.setattr("src.core.external_tools.shutil.which", lambda name: None)

    assert resolve_mkvmerge_path(str(tool)) is None
