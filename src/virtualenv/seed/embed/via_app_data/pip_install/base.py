from __future__ import absolute_import, unicode_literals

import logging
import os
import re
import zipfile
from abc import ABCMeta, abstractmethod
from itertools import chain
from tempfile import mkdtemp

from distlib.scripts import ScriptMaker, enquote_executable
from six import PY3, add_metaclass
from six.moves import shlex_quote

from virtualenv.util import ConfigParser
from virtualenv.util.path import Path, safe_delete
from virtualenv.util.six import ensure_text


@add_metaclass(ABCMeta)
class PipInstall(object):
    def __init__(self, wheel, creator, image_folder):
        self._wheel = wheel
        self._creator = creator
        self._image_dir = image_folder
        self._extracted = False
        self.__dist_info = None
        self._console_entry_points = None

    @abstractmethod
    def _sync(self, src, dst):
        raise NotImplementedError

    def install(self, version_info):
        self._extracted = True
        self._uninstall_previous_version()
        # sync image
        for filename in self._image_dir.iterdir():
            into = self._creator.purelib / filename.name
            self._sync(filename, into)
        # generate console executables
        consoles = set()
        script_dir = self._creator.script_dir
        for name, module in self._console_scripts.items():
            consoles.update(self._create_console_entry_point(name, module, script_dir, version_info))
        logging.debug("generated console scripts %s", " ".join(i.name for i in consoles))

    def build_image(self):
        # 1. first extract the wheel
        logging.debug("build install image for %s to %s", self._wheel.name, self._image_dir)
        with zipfile.ZipFile(str(self._wheel)) as zip_ref:
            self._shorten_path_if_needed(zip_ref)
            zip_ref.extractall(str(self._image_dir))
            self._extracted = True
        # 2. now add additional files not present in the distribution
        new_files = self._generate_new_files()
        # 3. finally fix the records file
        self._fix_records(new_files)

    def _shorten_path_if_needed(self, zip_ref):
        if os.name == "nt":
            to_folder = str(self._image_dir)
            # https://docs.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation
            zip_max_len = max(len(i) for i in zip_ref.namelist())
            path_len = zip_max_len + len(to_folder)
            if path_len > 260:
                self._image_dir.mkdir(exist_ok=True)  # to get a short path must exist

                from virtualenv.util.path import get_short_path_name

                to_folder = get_short_path_name(to_folder)
                self._image_dir = Path(to_folder)

    def _records_text(self, files):
        record_data = "\n".join(
            "{},,".format(os.path.relpath(ensure_text(str(rec)), ensure_text(str(self._image_dir)))) for rec in files
        )
        return record_data

    def _generate_new_files(self):
        new_files = set()
        installer = self._dist_info / "INSTALLER"
        installer.write_text("pip\n")
        new_files.add(installer)
        # inject a no-op root element, as workaround for bug in https://github.com/pypa/pip/issues/7226
        marker = self._image_dir / "{}.virtualenv".format(self._dist_info.stem)
        marker.write_text("")
        new_files.add(marker)
        folder = mkdtemp()
        try:
            to_folder = Path(folder)
            rel = os.path.relpath(ensure_text(str(self._creator.script_dir)), ensure_text(str(self._creator.purelib)))
            version_info = self._creator.interpreter.version_info
            for name, module in self._console_scripts.items():
                new_files.update(
                    Path(os.path.normpath(ensure_text(str(self._image_dir / rel / i.name))))
                    for i in self._create_console_entry_point(name, module, to_folder, version_info)
                )
        finally:
            safe_delete(folder)
        return new_files

    @property
    def _dist_info(self):
        if self._extracted is False:
            return None  # pragma: no cover
        if self.__dist_info is None:
            files = []
            for filename in self._image_dir.iterdir():
                files.append(filename.name)
                if filename.suffix == ".dist-info":
                    self.__dist_info = filename
                    break
            else:
                msg = "no .dist-info at {}, has {}".format(self._image_dir, ", ".join(files))  # pragma: no cover
                raise RuntimeError(msg)  # pragma: no cover
        return self.__dist_info

    @abstractmethod
    def _fix_records(self, extra_record_data):
        raise NotImplementedError

    @property
    def _console_scripts(self):
        if self._extracted is False:
            return None  # pragma: no cover
        if self._console_entry_points is None:
            self._console_entry_points = {}
            entry_points = self._dist_info / "entry_points.txt"
            if entry_points.exists():
                parser = ConfigParser.ConfigParser()
                with entry_points.open() as file_handler:
                    reader = getattr(parser, "read_file" if PY3 else "readfp")
                    reader(file_handler)
                if "console_scripts" in parser.sections():
                    for name, value in parser.items("console_scripts"):
                        match = re.match(r"(.*?)-?\d\.?\d*", name)
                        if match:
                            name = match.groups(1)[0]
                        self._console_entry_points[name] = value
        return self._console_entry_points

    def _create_console_entry_point(self, name, value, to_folder, version_info):
        result = []
        maker = ScriptMakerCustom(to_folder, version_info, self._creator.exe, name)
        specification = "{} = {}".format(name, value)
        new_files = maker.make(specification)
        result.extend(Path(i) for i in new_files)
        return result

    def _uninstall_previous_version(self):
        dist_name = self._dist_info.stem.split("-")[0]
        in_folders = chain.from_iterable([i.iterdir() for i in {self._creator.purelib, self._creator.platlib}])
        paths = (p for p in in_folders if p.stem.split("-")[0] == dist_name and p.suffix == ".dist-info" and p.is_dir())
        existing_dist = next(paths, None)
        if existing_dist is not None:
            self._uninstall_dist(existing_dist, self._creator.dest)

    @staticmethod
    def _uninstall_dist(dist, env_dir):
        dist_base = dist.parent
        logging.debug("uninstall existing distribution %s from %s", dist.stem, dist_base)

        top_txt = dist / "top_level.txt"  # add top level packages at folder level
        paths = {dist.parent / i.strip() for i in top_txt.read_text().splitlines()} if top_txt.exists() else set()
        paths.add(dist)  # add the dist-info folder itself

        base_dirs, record = paths.copy(), dist / "RECORD"  # collect entries in record that we did not register yet
        for name in (i.split(",")[0] for i in record.read_text().splitlines()) if record.exists() else ():
            path = dist_base / name
            if not any(p in base_dirs for p in path.parents):  # only add if not already added as a base dir
                paths.add(path)

        # metadata is untrusted: only remove entries inside the environment, never the environment itself or a folder
        # holding the metadata (a blank top_level.txt line names site-packages)
        root = env_dir.resolve()
        metadata_parents = set(dist.resolve().parents)
        for entry in sorted(paths):  # actually remove stuff in a stable order
            if entry.exists() or entry.is_symlink():
                linked = entry.is_symlink()
                # unlinking the final link leaves its target intact; parent links still affect containment
                resolved = entry.parent.resolve() / entry.name if linked else entry.resolve()
                if root not in resolved.parents or resolved in metadata_parents:
                    logging.warning(
                        "skip removal of %s listed by %s: not inside environment %s or a parent of the metadata",
                        entry,
                        dist.name,
                        root,
                    )
                elif entry.is_dir() and not linked:
                    safe_delete(entry)
                else:
                    entry.unlink()

    def clear(self):
        if self._image_dir.exists():
            safe_delete(self._image_dir)

    def has_image(self):
        return self._image_dir.exists() and next(self._image_dir.iterdir()) is not None


class ScriptMakerCustom(ScriptMaker):
    def __init__(self, target_dir, version_info, executable, name):
        super(ScriptMakerCustom, self).__init__(None, str(target_dir))
        self.clobber = True  # overwrite
        self.set_mode = True  # ensure they are executable
        self.executable = enquote_executable(str(executable))
        self.version_info = version_info.major, version_info.minor
        self.variants = {"", "X", "X.Y"}
        self._name = name
        self._raw_executable = ensure_text(str(executable))

    def _build_shebang(self, executable, post_interp):
        shebang = super(ScriptMakerCustom, self)._build_shebang(executable, post_interp)
        if os.name != "posix" or len(shebang.split()) == 1:
            return shebang
        # distlib only double quotes the interpreter path for the /bin/sh launcher, so the shell would still expand
        # $(...), backticks and $VAR from the destination path; it also misses tabs when choosing that launcher
        return shell_shebang(self._raw_executable, post_interp)

    def _write_script(self, names, shebang, script_bytes, filenames, ext):
        names.add("{}{}.{}".format(self._name, *self.version_info))
        for name in names:  # distlib opens the script path directly, so a planted (dangling) link would be followed
            path = Path(self.target_dir) / ("{}.exe".format(name) if os.name == "nt" else name)
            if path.is_symlink():
                path.unlink()
        super(ScriptMakerCustom, self)._write_script(names, shebang, script_bytes, filenames, ext)


def shell_shebang(executable, post_interp=b""):
    # The exec line is read by both sh and Python; double-quoted backslashes survive both readers.
    quoted = shlex_quote(ensure_text(executable)).replace("\\", "'\"\\\\\"'")
    return b"#!/bin/sh\n'''exec' " + quoted.encode("utf-8") + post_interp + b' "$0" "$@"\n' + b"' '''\n"
