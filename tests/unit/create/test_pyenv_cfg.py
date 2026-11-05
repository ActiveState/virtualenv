# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from collections import OrderedDict

import pytest

from virtualenv.create.pyenv_cfg import PyEnvCfg
from virtualenv.run import cli_run
from virtualenv.util.path import Path
from virtualenv.util.six import ensure_text
from virtualenv.util.text import collapse_line_boundaries

BOUNDARIES = ["\n", "\r", "\r\n", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"]


@pytest.mark.parametrize("boundary", BOUNDARIES, ids=[repr(b) for b in BOUNDARIES])
def test_pyenv_cfg_value_stays_on_one_line(tmp_path, boundary):
    """GHSA-9h9j-4vrj-gf7g: a value must never be read back as extra configuration lines."""
    path = Path(ensure_text(str(tmp_path))) / "pyvenv.cfg"
    cfg = PyEnvCfg(OrderedDict(), path)
    cfg["include-system-site-packages"] = "false"
    cfg["prompt"] = "x{}include-system-site-packages = true".format(boundary)
    cfg.write()

    content = PyEnvCfg.from_file(path).content
    assert list(content) == ["include-system-site-packages", "prompt"]
    assert content["include-system-site-packages"] == "false"
    assert path.read_text(encoding="utf-8").count("\n") == 2


def test_collapse_line_boundaries_keeps_other_text():
    assert collapse_line_boundaries("a b\tc ünï") == "a b\tc ünï"
    assert collapse_line_boundaries("".join(BOUNDARIES)).splitlines() == [" " * len("".join(BOUNDARIES))]


def test_prompt_cannot_inject_pyvenv_cfg_keys(tmp_path, current_fastest):
    prompt = "x\ninclude-system-site-packages = true\nhome = /attacker"
    session = cli_run(
        [
            ensure_text(str(tmp_path / "env")),
            "--without-pip",
            "--creator",
            current_fastest,
            "--no-periodic-update",
            "--prompt",
            prompt,
        ],
    )
    content = PyEnvCfg.from_file(session.creator.pyenv_cfg.path).content
    assert content["include-system-site-packages"] == "false"
    assert content["home"] != "/attacker"
    assert content["prompt"] == "x include-system-site-packages = true home = /attacker"
