"""Windows venv path helpers."""

import os

from sia.layout import venv_pip_path, venv_python_path


def test_venv_python_path_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "name", "nt")
    venv = str(tmp_path / "venv")
    assert venv_python_path(venv).endswith(os.path.join("Scripts", "python.exe"))


def test_venv_python_path_unix(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "name", "posix")
    venv = str(tmp_path / "venv")
    assert venv_python_path(venv).endswith(os.path.join("bin", "python"))


def test_venv_pip_path_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "name", "nt")
    venv = str(tmp_path / "venv")
    assert venv_pip_path(venv).endswith(os.path.join("Scripts", "pip.exe"))
