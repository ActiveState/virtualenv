from __future__ import absolute_import, unicode_literals

import errno
import io
import logging
import os
import shutil
from stat import S_ISDIR, S_ISLNK, S_IWUSR, S_IXGRP, S_IXOTH, S_IXUSR

from six import PY2

from virtualenv.info import IS_CPYTHON, IS_WIN
from virtualenv.util.six import ensure_text

from ._pathlib import Path

if PY2 and IS_CPYTHON and IS_WIN:  # CPython2 on Windows supports unicode paths if passed as unicode

    def norm(src):
        return ensure_text(str(src))

else:
    norm = str


def ensure_dir(path):
    if not path.exists():
        logging.debug("create folder %s", ensure_text(str(path)))
        os.makedirs(norm(path))


_IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003  # stat.IO_REPARSE_TAG_MOUNT_POINT, only exposed by Python 3.8+


def _is_junction(metadata):
    # st_reparse_tag only exists on Windows with Python 3.8+, older interpreters cannot tell a junction apart
    return IS_WIN and getattr(metadata, "st_reparse_tag", 0) == _IO_REPARSE_TAG_MOUNT_POINT


def ensure_within(root, path):
    """Create path (a folder within root) so that every component is a real directory, replacing planted links."""
    parts = path.relative_to(root).parts
    if ".." in parts:
        raise ValueError("environment directory {} must remain inside {}".format(path, root))
    ensure_dir(root)
    folder = root
    for part in parts:
        folder = folder / part
        name = norm(folder)
        try:
            metadata = os.lstat(name)
        except OSError as exception:
            if exception.errno != errno.ENOENT:
                raise
        else:
            if S_ISLNK(metadata.st_mode):
                logging.warning("replace environment directory link %s", ensure_text(str(folder)))
                try:
                    os.unlink(name)
                except OSError:
                    if not IS_WIN:
                        raise
                    os.rmdir(name)  # directory symlinks on Windows Python 2
            elif _is_junction(metadata):
                logging.warning("replace environment directory junction %s", ensure_text(str(folder)))
                os.rmdir(name)
        try:
            os.mkdir(name)
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                raise
            created = os.lstat(name)
            if not S_ISDIR(created.st_mode) or _is_junction(created):
                # on Python 3 the errno makes this a NotADirectoryError
                msg = "environment directory is not a real directory: {}".format(ensure_text(str(folder)))
                raise OSError(errno.ENOTDIR, msg)


def write_file(path, data):
    """Write data to a new file at path, replacing (not following) an existing file or symbolic/hard link."""
    if path.is_symlink() or path.exists():
        path.unlink()
    # exclusive creation rejects links introduced after the old entry was removed
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    with io.open(os.open(norm(path), flags, 0o666), "wb") as stream:
        stream.write(data)


def ensure_safe_to_do(src, dest):
    if src == dest:
        raise ValueError("source and destination is the same {}".format(src))
    if not dest.exists():
        return
    if dest.is_dir() and not dest.is_symlink():
        logging.debug("remove directory %s", dest)
        safe_delete(dest)
    else:
        logging.debug("remove file %s", dest)
        dest.unlink()


def symlink(src, dest):
    ensure_safe_to_do(src, dest)
    logging.debug("symlink %s", _Debug(src, dest))
    dest.symlink_to(src, target_is_directory=src.is_dir())


def copy(src, dest):
    logging.debug("copy %s", _Debug(src, dest))
    if src.is_dir():
        ensure_safe_to_do(src, dest)
        copytree(norm(src), norm(dest))
    else:
        _copy_file(src, dest)


def copytree(src, dest):
    for root, _, files in os.walk(src):
        dest_dir = os.path.join(dest, os.path.relpath(root, src))
        try:
            os.makedirs(dest_dir)
        except OSError as exception:
            if exception.errno != errno.EEXIST or not os.path.isdir(dest_dir):
                raise
        for name in files:
            _copy_file(Path(os.path.join(root, name)), Path(os.path.join(dest_dir, name)))


def _copy_file(src, dest):
    ensure_safe_to_do(src, dest)
    # derive the mode from the executable bit only, so permissions carried by the source (e.g. an app data cache
    # created under an older, more permissive umask) are not transferred; creation applies the current umask
    mode = 0o755 if os.stat(norm(src)).st_mode & (S_IXUSR | S_IXGRP | S_IXOTH) else 0o644
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    with io.open(norm(src), "rb") as source:
        with io.open(os.open(norm(dest), flags, mode), "wb") as target:
            shutil.copyfileobj(source, target, 1024 * 1024)


def safe_delete(dest):
    def onerror(func, path, exc_info):
        if not os.access(path, os.W_OK):
            os.chmod(path, S_IWUSR)
            func(path)
        else:
            raise

    shutil.rmtree(ensure_text(str(dest)), ignore_errors=True, onerror=onerror)


class _Debug(object):
    def __init__(self, src, dest):
        self.src = src
        self.dest = dest

    def __str__(self):
        return "{}{} to {}".format(
            "directory " if self.src.is_dir() else "",
            ensure_text(str(self.src)),
            ensure_text(str(self.dest)),
        )


__all__ = (
    "ensure_dir",
    "ensure_within",
    "write_file",
    "symlink",
    "copy",
    "symlink",
    "copytree",
    "safe_delete",
)
