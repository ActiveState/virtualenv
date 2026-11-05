from __future__ import absolute_import, unicode_literals

import os
import subprocess
from distutils.spawn import find_executable

import pytest

from virtualenv.activation import FishActivator
from virtualenv.info import IS_WIN
from virtualenv.run import cli_run
from virtualenv.util.six import ensure_text


@pytest.mark.skipif(IS_WIN, reason="we have not setup fish in CI yet")
def test_fish(activation_tester_class, activation_tester, monkeypatch, tmp_path):
    monkeypatch.setenv(str("HOME"), str(tmp_path))
    fish_conf_dir = tmp_path / ".config" / "fish"
    fish_conf_dir.mkdir(parents=True)
    (fish_conf_dir / "config.fish").write_text("")

    class Fish(activation_tester_class):
        def __init__(self, session):
            super(Fish, self).__init__(FishActivator, session, "fish", "activate.fish", "fish")

        def print_prompt(self):
            return "fish_prompt"

    activation_tester(Fish)


@pytest.mark.skipif(IS_WIN, reason="fish is not available on Windows")
@pytest.mark.skipif(find_executable("fish") is None, reason="fish is not installed")
@pytest.mark.parametrize(
    "prompt, env_name",
    [
        pytest.param("x\\'$(touch PWNED)'\\'", "env", id="prompt-backslash-quote-dollar"),
        pytest.param("x\\'(touch PWNED)'\\'", "env", id="prompt-backslash-quote"),
        pytest.param(None, "x\\'$(touch PWNED)'\\'", id="dirname-backslash-quote-dollar"),
        pytest.param(None, "x\\'(touch PWNED)'\\'", id="dirname-backslash-quote"),
        pytest.param(None, "x'(touch PWNED)'y", id="dirname-quote"),
        pytest.param(None, 'x"(touch PWNED)"y', id="dirname-double-quote"),
    ],
)
def test_fish_activate_does_not_run_commands(tmp_path, current_fastest, prompt, env_name):
    """GHSA-c947-3pg5-gm8q (backslash before quote) and GHSA-p58f-9548-mpm2 (commands embedded in paths)."""
    dest = tmp_path / env_name
    args = [ensure_text(str(dest)), "--without-pip", "--creator", current_fastest, "--no-periodic-update"]
    args += ["--activators", "fish"]
    if prompt is not None:
        args += ["--prompt", prompt]
    cli_run(args)
    work_dir = tmp_path / "workdir"
    work_dir.mkdir()
    (tmp_path / "home").mkdir()
    env = os.environ.copy()
    env[str("HOME")] = str(tmp_path / "home")
    # the path is passed through the environment so the driver cannot expand a payload dir name while locating the
    # script (fish before 3.1 does not set $argv for -c)
    env[str("_ACTIVATE_UNDER_TEST")] = str(dest / "bin" / "activate.fish")

    script = 'source "$_ACTIVATE_UNDER_TEST"; printf "%s|" "$VIRTUAL_ENV"; fish_prompt'
    cmd = [find_executable("fish"), "-c", script]
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=ensure_text(str(work_dir)),
        env=env,
    )
    out, err = process.communicate()
    out, err = out.decode("utf-8"), err.decode("utf-8")

    assert not (work_dir / "PWNED").exists(), err
    assert out.startswith("{}|".format(ensure_text(str(dest)))), (out, err)
    assert "({}) ".format(prompt if prompt is not None else env_name) in out, (out, err)
