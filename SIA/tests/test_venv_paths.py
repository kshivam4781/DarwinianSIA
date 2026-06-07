"""Tests for cross-platform venv executable paths."""

import os
import sys

import pytest

from sia.layout import venv_pip_path, venv_python_path


@pytest.mark.parametrize(
    "platform",
    ["win32", "linux", "darwin"],
)
def test_venv_paths_by_platform(platform, monkeypatch):
    monkeypatch.setattr(sys, "platform", platform)
    venv_dir = r"C:\fake\venv" if platform == "win32" else "/fake/venv"
    py = venv_python_path(venv_dir)
    pip = venv_pip_path(venv_dir)
    if platform == "win32":
        assert py == os.path.join(venv_dir, "Scripts", "python.exe")
        assert pip == os.path.join(venv_dir, "Scripts", "pip.exe")
    else:
        assert py == os.path.join(venv_dir, "bin", "python")
        assert pip == os.path.join(venv_dir, "bin", "pip")


def test_venv_paths_windows_use_scripts():
    if sys.platform != "win32":
        pytest.skip("Windows-only assertion")
    venv_dir = r"C:\runs\run_1\venv"
    assert venv_python_path(venv_dir) == os.path.join(venv_dir, "Scripts", "python.exe")
    assert venv_pip_path(venv_dir) == os.path.join(venv_dir, "Scripts", "pip.exe")
