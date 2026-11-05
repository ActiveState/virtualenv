from __future__ import absolute_import, unicode_literals

import logging
import os
from argparse import ArgumentTypeError
from itertools import chain

from virtualenv.create.via_global_ref.store import handle_store_python
from virtualenv.discovery.py_info import PythonInfo
from virtualenv.util.error import ProcessCallFailed
from virtualenv.util.path import ensure_within
from virtualenv.util.six import ensure_text
from virtualenv.util.subprocess import run_cmd
from virtualenv.util.text import collapse_line_boundaries

from .api import ViaGlobalRefApi, ViaGlobalRefMeta
from .builtin.pypy.pypy3 import Pypy3Windows


class Venv(ViaGlobalRefApi):
    def __init__(self, options, interpreter):
        self.describe = options.describe
        super(Venv, self).__init__(options, interpreter)
        self.can_be_inline = (
            interpreter is PythonInfo.current() and interpreter.executable == interpreter.system_executable
        )
        self._context = None

    def _args(self):
        return super(Venv, self)._args() + ([("describe", self.describe.__class__.__name__)] if self.describe else [])

    @classmethod
    def can_create(cls, interpreter):
        if interpreter.has_venv:
            meta = ViaGlobalRefMeta()
            if interpreter.platform == "win32" and interpreter.version_info.major == 3:
                meta = handle_store_python(meta, interpreter)
            return meta
        return None

    def create(self):
        # stdlib venv writes interpreter files, configuration and activation scripts in place, so a planted symlink or
        # hard link would receive them outside the environment
        for directory in (self.bin_dir, self.purelib, self.platlib):
            ensure_within(self.dest, directory)
        for path in chain((self.dest / "pyvenv.cfg", self.dest / ".gitignore"), self.bin_dir.iterdir()):
            if path.is_symlink() or (path.is_file() and path.stat().st_nlink > 1):
                path.unlink()
        if self.can_be_inline:
            self.create_inline()
        else:
            self.create_via_sub_process()
        super(Venv, self).create()
        self.executables_for_win_pypy_less_v37()

    @classmethod
    def validate_dest(cls, raw_value):
        return cls._check_line_boundaries(super(Venv, cls).validate_dest(cls._check_line_boundaries(raw_value)))

    @staticmethod
    def _check_line_boundaries(value):
        # stdlib venv writes the destination into pyvenv.cfg without escaping line boundaries.
        text = ensure_text(value)
        if collapse_line_boundaries(text) != text:
            raise ArgumentTypeError(
                "destination {!r} must not contain a line boundary as venv cannot record it in pyvenv.cfg".format(
                    text,
                ),
            )
        return value

    def executables_for_win_pypy_less_v37(self):
        """
        PyPy <= 3.6 (v7.3.3) for Windows contains only pypy3.exe and pypy3w.exe
        Venv does not handle non-existing exe sources, e.g. python.exe, so this
        patch does it.
        """
        creator = self.describe
        if isinstance(creator, Pypy3Windows) and creator.less_v37:
            for exe in creator.executables(self.interpreter):
                exe.run(creator, self.symlinks)

    def create_inline(self):
        from venv import EnvBuilder

        builder = EnvBuilder(
            system_site_packages=self.enable_system_site_package,
            clear=False,
            symlinks=self.symlinks,
            with_pip=False,
        )
        builder.create(str(self.dest))

    def create_via_sub_process(self):
        cmd = self.get_host_create_cmd()
        logging.info("using host built-in venv to create via %s", " ".join(cmd))
        code, out, err = run_cmd(cmd)
        if code != 0:
            raise ProcessCallFailed(code, out, err, cmd)

    def get_host_create_cmd(self):
        cmd = [self.interpreter.system_executable, "-m", "venv", "--without-pip"]
        if self.enable_system_site_package:
            cmd.append("--system-site-packages")
        cmd.append("--symlinks" if self.symlinks else "--copies")
        cmd.append(str(self.dest))
        return cmd

    def set_pyenv_cfg(self):
        # write the configuration from the selected interpreter and our options only: reading back stdlib venv's
        # intermediate pyvenv.cfg would let a crafted value (e.g. a destination embedded in its command line)
        # be reinterpreted as additional keys; the keys stdlib venv contributed are derived from the interpreter instead
        super(Venv, self).set_pyenv_cfg()
        system_executable = self.interpreter.system_executable or self.interpreter.executable
        self.pyenv_cfg["home"] = os.path.dirname(os.path.abspath(system_executable))
        self.pyenv_cfg["version"] = ".".join(str(i) for i in self.interpreter.version_info[:3])
        if self.interpreter.version_info[:2] >= (3, 11):
            self.pyenv_cfg["executable"] = os.path.realpath(system_executable)

    def __getattribute__(self, item):
        describe = object.__getattribute__(self, "describe")
        if describe is not None and hasattr(describe, item):
            element = getattr(describe, item)
            if not callable(element) or item in ("script",):
                return element
        return object.__getattribute__(self, item)
