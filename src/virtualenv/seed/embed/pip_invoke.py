from __future__ import absolute_import, unicode_literals

import csv
import hashlib
import logging
import os
from base64 import urlsafe_b64encode
from contextlib import contextmanager
from shutil import copyfile
from stat import S_IMODE
from tempfile import mkdtemp

from six import PY2

from virtualenv.discovery.cached_py_info import LogCmd
from virtualenv.seed.embed.base_embed import BaseEmbed
from virtualenv.seed.embed.via_app_data.pip_install.base import shell_shebang
from virtualenv.util.path import safe_delete
from virtualenv.util.six import ensure_text
from virtualenv.util.subprocess import Popen

from ..wheels import Version, get_wheel, pip_wheel_env_run


class PipInvoke(BaseEmbed):
    def __init__(self, options):
        super(PipInvoke, self).__init__(options)

    def run(self, creator):
        if not self.enabled:
            return
        for_py_version = creator.interpreter.version_release_str
        with self.get_pip_install_cmd(creator.exe, for_py_version) as cmd:
            env = pip_wheel_env_run(self.extra_search_dir, self.app_data, self.env)
            self._execute(cmd, env)
        if os.name == "posix":
            self._rewrite_launchers(creator)

    def _rewrite_launchers(self, creator):
        """
        pip writes the same /bin/sh launcher as distlib when the interpreter path holds a space or is too long, with the
        path only double quoted (so the shell expands $(...), backticks and $VAR in it); re-quote those launchers.
        """
        selected = {_canonical(dist) for dist in self.distribution_to_versions()}
        exe = ensure_text(str(creator.exe)).encode("utf-8")
        script_dir = os.path.abspath(ensure_text(str(creator.script_dir)))
        for lib in sorted({ensure_text(str(creator.purelib)), ensure_text(str(creator.platlib))}):
            if not os.path.isdir(lib):
                continue
            for name in sorted(os.listdir(lib)):
                if not name.endswith(".dist-info") or _canonical(name.split("-")[0]) not in selected:
                    continue
                record = os.path.join(lib, name, "RECORD")
                if not os.path.isfile(record):
                    continue
                rows = _read_record(record)
                changed = False
                for row in rows:
                    if not row:
                        continue
                    path = os.path.abspath(os.path.join(lib, row[0]))
                    if os.path.dirname(path) != script_dir or not os.path.isfile(path):
                        continue
                    with open(path, "rb") as file_handler:
                        content = file_handler.read()
                    if content.startswith(b"#!/bin/sh\n'''exec' "):
                        body = content.split(b"\n", 3)[3]
                    elif content.startswith(b"#!" + exe + b"\n") and len(exe.split()) > 1:
                        body = content.split(b"\n", 1)[1]
                    else:
                        continue
                    content = shell_shebang(ensure_text(str(creator.exe))) + body
                    mode = S_IMODE(os.stat(path).st_mode) & 0o755
                    os.unlink(path)
                    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode), "wb") as file_handler:
                        file_handler.write(content)
                    digest = urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
                    row[1:] = ["sha256={}".format(digest), str(len(content))]
                    changed = True
                if changed:
                    _write_record(record, rows)

    @staticmethod
    def _execute(cmd, env):
        logging.debug("pip seed by running: %s", LogCmd(cmd, env))
        process = Popen(cmd, env=env)
        process.communicate()
        if process.returncode != 0:
            raise RuntimeError("failed seed with code {}".format(process.returncode))
        return process

    @contextmanager
    def get_pip_install_cmd(self, exe, for_py_version):
        cmd = [
            str(exe),
            "-m",
            "pip",
            "-q",
            "install",
            "--only-binary",
            ":all:",
            "--disable-pip-version-check",
            "--no-index",
            "--no-deps",
        ]
        # Only the selected (and, when downloaded, verified) archives may participate in pip's filename-based
        # selection: never let pip consult an index or a shared folder holding other candidates. --no-deps matches the
        # app-data seeder, which never installs dependencies either: a newer downloaded wheel (e.g. wheel>=0.46, which
        # requires packaging) must not make pip go looking for unverified archives it was not given.
        folder = mkdtemp(prefix="virtualenv-seed-")
        try:
            cmd.extend(["--find-links", folder])
            for dist, version in self.distribution_to_versions().items():
                wheel = get_wheel(
                    distribution=dist,
                    version=version,
                    for_py_version=for_py_version,
                    search_dirs=self.extra_search_dir,
                    download=self.download,
                    app_data=self.app_data,
                    do_periodic_update=self.periodic_update,
                    env=self.env,
                )
                if wheel is None:
                    raise RuntimeError("could not get wheel for distribution {}".format(dist))
                copyfile(str(wheel.path), os.path.join(folder, wheel.name))
                cmd.append(Version.as_pip_req(dist, wheel.version))
            yield cmd
        finally:
            safe_delete(folder)


def _canonical(name):
    return name.lower().replace("-", "_")


def _read_record(record):
    if PY2:
        with open(record, "rb") as file_handler:
            return [[cell.decode("utf-8") for cell in row] for row in csv.reader(file_handler)]
    with open(record, encoding="utf-8", newline="") as file_handler:
        return list(csv.reader(file_handler))


def _write_record(record, rows):
    if PY2:
        with open(record, "wb") as file_handler:
            csv.writer(file_handler).writerows([[cell.encode("utf-8") for cell in row] for row in rows])
    else:
        with open(record, "w", encoding="utf-8", newline="") as file_handler:
            csv.writer(file_handler).writerows(rows)
