from __future__ import absolute_import, unicode_literals

import logging
import os
from contextlib import contextmanager
from shutil import copyfile
from tempfile import mkdtemp

from virtualenv.discovery.cached_py_info import LogCmd
from virtualenv.seed.embed.base_embed import BaseEmbed
from virtualenv.util.path import safe_delete
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
        ]
        # Only the selected (and, when downloaded, verified) archives may participate in pip's filename-based
        # selection: never let pip consult an index or a shared folder holding other candidates.
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
