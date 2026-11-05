from __future__ import absolute_import, unicode_literals

import os
import subprocess
import sys

import pytest

from virtualenv.info import IS_WIN, PY2
from virtualenv.util.path import Path, copy, ensure_within, write_file
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


@pytest.mark.parametrize("existing", [pytest.param(False, id="new"), pytest.param(True, id="existing")])
def test_environment_directories_create_nested_path(tmp_path, existing):
    root = Path(str(tmp_path))
    folder = root / "env" / "lib" / "python"
    if existing:
        folder.mkdir(parents=True)
    ensure_within(root / "env", folder)
    assert folder.is_dir()


def test_environment_directories_reject_regular_file(tmp_path):
    root = Path(str(tmp_path))
    folder = root / "file"
    folder.write_bytes(b"")
    with pytest.raises(OSError, match="not a real directory"):
        ensure_within(root, folder)


def test_environment_directories_reject_parent_components(tmp_path):
    root = Path(str(tmp_path))
    with pytest.raises(ValueError, match="must remain inside"):
        ensure_within(root, root / ".." / "folder")


@pytest.mark.skipif(not hasattr(os, "symlink") or IS_WIN, reason="symlinks are unavailable")
@pytest.mark.parametrize(
    "existing",
    [pytest.param(False, id="missing-target"), pytest.param(True, id="existing-target")],
)
def test_environment_directories_remove_links(tmp_path, caplog, existing):
    root = Path(str(tmp_path))
    target = root / "stored"
    if existing:
        target.mkdir()
    link = root / "link"
    link.symlink_to(target, target_is_directory=True)
    ensure_within(root, link / "nested")
    assert (
        link.is_symlink(),
        link.exists(),
        target.exists(),
        "replace environment directory link {}".format(link) in caplog.text,
    ) == (False, True, existing, True)


@pytest.mark.skipif(os.name != "nt" or sys.version_info < (3, 8), reason="Windows junctions")
def test_environment_directories_report_replaced_junction(tmp_path, caplog):
    root = Path(str(tmp_path))
    target = root / "stored"
    target.mkdir()
    link = root / "link"
    subprocess.check_call(["cmd", "/c", "mklink", "/J", str(link), str(target)])
    ensure_within(root, link)
    assert (link.resolve(), "replace environment directory junction {}".format(link) in caplog.text) == (link, True)
