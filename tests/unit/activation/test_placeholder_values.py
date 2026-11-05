from __future__ import absolute_import, unicode_literals

import os
import re
import subprocess
import sys
from argparse import Namespace
from distutils.spawn import find_executable

import pytest

from virtualenv.activation import (
    BashActivator,
    BatchActivator,
    CShellActivator,
    FishActivator,
    NushellActivator,
    PowerShellActivator,
    PythonActivator,
)
from virtualenv.info import IS_WIN
from virtualenv.util.path import Path
from virtualenv.util.six import ensure_text

# a value holding another placeholder's name must stay data: GHSA-8rjx-v5ww-45pp / CVE-2026-113776
PLACEHOLDERS = ["__VIRTUAL_NAME__", "__VIRTUAL_ENV__", "__VIRTUAL_PROMPT__", "__BIN_NAME__", "__PATH_SEP__"]


class _Interpreter(object):
    os = "nt" if IS_WIN else "posix"
    platform = sys.platform
    version_info = sys.version_info


class _Creator(object):
    def __init__(self, dest):
        self.dest = dest
        self.bin_dir = dest / "bin"
        self.bin_dir.mkdir(parents=True)
        self.interpreter = _Interpreter()
        self.pyenv_cfg = {}
        self.env_name = dest.name
        self.libs = [dest / "lib"]


@pytest.mark.parametrize(
    "activator_class",
    [
        BashActivator,
        BatchActivator,
        CShellActivator,
        FishActivator,
        NushellActivator,
        PowerShellActivator,
        PythonActivator,
    ],
)
@pytest.mark.parametrize("placeholder", PLACEHOLDERS)
def test_placeholder_name_in_value_stays_data(tmp_path, activator_class, placeholder):
    dest = Path(ensure_text(str(tmp_path))) / "A{}B".format(placeholder) / "x'y"
    creator = _Creator(dest)
    activator = activator_class(Namespace(prompt="p{}q".format(placeholder)))
    replacements = activator.replacements(creator, creator.bin_dir)

    for template in activator.templates():
        source = activator.instantiate_template({}, template, creator)  # the raw template, nothing substituted
        text = activator.instantiate_template(replacements, template, creator)
        for key, value in replacements.items():
            expected = activator.quote(activator._repr_unicode(creator, value))
            assert text.count(expected) >= source.count(key), (template, key, text)
        rest = _strip(text, replacements, activator, creator)
        assert not re.search(r"__(VIRTUAL_ENV|BIN_NAME|PATH_SEP|DEACTIVATE_PATH|LIB_FOLDERS|DECODE_PATH)__", rest), text


def _strip(text, replacements, activator, creator):
    # remove every substituted value; no placeholder may remain outside them
    quoted = [activator.quote(activator._repr_unicode(creator, value)) for value in replacements.values()]
    for value in sorted(quoted, key=len, reverse=True):  # longest first, a short value can be part of a longer one
        text = text.replace(value, "")
    return text


@pytest.mark.skipif(IS_WIN or find_executable("csh") is None, reason="needs csh")
def test_csh_placeholder_in_parent_dir_does_not_run_commands(tmp_path):
    dest = os.path.join(ensure_text(str(tmp_path)), "A__VIRTUAL_NAME__B", "x'`touch PWNED`'y")
    subprocess.check_call([sys.executable, "-m", "virtualenv", dest, "--without-pip", "--activators", "cshell"])
    work_dir = os.path.join(ensure_text(str(tmp_path)), "workdir")
    os.mkdir(work_dir)
    env = os.environ.copy()
    env[str("_ACTIVATE_UNDER_TEST")] = str(os.path.join(dest, "bin", "activate.csh"))
    process = subprocess.Popen(
        ["csh", "-f", "-c", 'source "$_ACTIVATE_UNDER_TEST"; echo "$VIRTUAL_ENV"'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=work_dir,
        env=env,
    )
    out, err = process.communicate()
    assert not os.path.exists(os.path.join(work_dir, "PWNED")), err
    assert out.decode("utf-8").strip() == dest, err


def test_python_placeholder_in_parent_dir_stays_data(tmp_path):
    dest = os.path.join(ensure_text(str(tmp_path)), "A__BIN_NAME__B", "x'__import__('os').mkdir('PWNED')'y")
    subprocess.check_call([sys.executable, "-m", "virtualenv", dest, "--without-pip", "--activators", "python"])
    work_dir = os.path.join(ensure_text(str(tmp_path)), "workdir")
    os.mkdir(work_dir)
    script = os.path.join(dest, "bin", "activate_this.py")
    code = "f = {!r}; exec(open(f).read(), {{'__file__': f}}); import os; print(os.environ['VIRTUAL_ENV'])".format(
        str(script),
    )
    out = subprocess.check_output([sys.executable, "-c", code], cwd=work_dir)
    assert not os.path.exists(os.path.join(work_dir, "PWNED"))
    assert out.decode("utf-8").strip() == dest
