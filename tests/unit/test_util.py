from __future__ import absolute_import, unicode_literals

import os
import subprocess
import sys

import pytest

from virtualenv.info import IS_WIN, PY2
from virtualenv.util.path import Path, copy, write_file
from virtualenv.util.subprocess import run_cmd


def test_run_fail(tmp_path):
    code, out, err = run_cmd([str(tmp_path)])
    assert err
    assert not out
    assert code


@pytest.mark.skipif(not (PY2 and IS_WIN), reason="subprocess patch only applied on Windows python2")
def test_windows_py2_cwd_works(tmp_path):
    cwd = str(tmp_path)
    result = subprocess.check_output(
        [sys.executable, "-c", "import os; print(os.getcwd())"],
        cwd=cwd,
        universal_newlines=True,
    )
    assert result == "{}\n".format(cwd)


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
@pytest.mark.parametrize("directory", [pytest.param(False, id="file"), pytest.param(True, id="tree")])
@pytest.mark.parametrize(
    ("source_mode", "mask", "expected"),
    [
        pytest.param(0o666, 0o022, 0o644, id="normal"),
        pytest.param(0o666, 0o077, 0o600, id="private"),
        pytest.param(0o444, 0o022, 0o644, id="read-only-source"),
        pytest.param(0o600, 0o022, 0o644, id="private-source"),
        pytest.param(0o777, 0o022, 0o755, id="executable"),
        pytest.param(0o777, 0o077, 0o700, id="private-executable"),
        pytest.param(0o666, 0o000, 0o644, id="permissive-umask"),
        pytest.param(0o777, 0o000, 0o755, id="permissive-executable"),
        pytest.param(0o666, 0o002, 0o644, id="group-umask"),
        pytest.param(0o777, 0o002, 0o755, id="group-executable"),
    ],
)
def test_copy_uses_current_umask(tmp_path, directory, source_mode, mask, expected):
    root = Path(str(tmp_path))
    source = root / "source"
    source.mkdir()
    payload = source / "entry"
    payload.write_bytes(b"copied bytes")
    payload.chmod(source_mode)
    destination = root / "destination"
    previous = os.umask(mask)
    try:
        copy(source if directory else payload, destination)
    finally:
        os.umask(previous)
    result = destination / "entry" if directory else destination
    assert (result.read_bytes(), result.stat().st_mode & 0o777) == (b"copied bytes", expected)


@pytest.mark.parametrize("directory", [pytest.param(False, id="file"), pytest.param(True, id="tree")])
def test_copy_replaces_contents(tmp_path, directory):
    root = Path(str(tmp_path))
    source = root / "source"
    source.mkdir()
    (source / "entry").write_bytes(b"new")
    destination = root / "destination"
    destination.write_bytes(b"old")
    copy(source if directory else source / "entry", destination)
    assert (destination / "entry" if directory else destination).read_bytes() == b"new"


@pytest.mark.parametrize("existing", [pytest.param(False, id="new"), pytest.param(True, id="replace")])
def test_write_file_replaces_content(tmp_path, existing):
    path = Path(str(tmp_path)) / "generated"
    if existing:
        path.write_bytes(b"previous")
    write_file(path, b"generated")
    assert path.read_bytes() == b"generated"


@pytest.mark.skipif(not hasattr(os, "symlink") or IS_WIN, reason="requires symlinks")
@pytest.mark.parametrize("existing", [pytest.param(False, id="dangling"), pytest.param(True, id="existing")])
def test_write_file_replaces_link(tmp_path, existing):
    root = Path(str(tmp_path))
    target = root / "target"
    if existing:
        target.write_bytes(b"original")
    path = root / "generated"
    path.symlink_to(target)
    write_file(path, b"generated")
    assert (path.is_symlink(), path.read_bytes(), target.read_bytes() if existing else target.exists()) == (
        False,
        b"generated",
        b"original" if existing else False,
    )
