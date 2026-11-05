from __future__ import absolute_import, unicode_literals

import os
import subprocess
import sys
from distutils.spawn import find_executable

import pytest

from virtualenv.activation import PowerShellActivator
from virtualenv.run import cli_run
from virtualenv.util.six import ensure_text


@pytest.mark.slow
def test_powershell(activation_tester_class, activation_tester, monkeypatch):
    monkeypatch.setenv("TERM", "xterm")

    class PowerShell(activation_tester_class):
        def __init__(self, session):
            cmd = "powershell.exe" if sys.platform == "win32" else "pwsh"
            super(PowerShell, self).__init__(PowerShellActivator, session, cmd, "activate.ps1", "ps1")
            self._version_cmd = [cmd, "-c", "$PSVersionTable"]
            self._invoke_script = [cmd, "-ExecutionPolicy", "ByPass", "-File"]
            self.activate_cmd = "."
            self.script_encoding = "utf-16"

        def _get_test_lines(self, activate_script):
            # for BATCH utf-8 support need change the character code page to 650001
            return super(PowerShell, self)._get_test_lines(activate_script)

        def invoke_script(self):
            return [self.cmd, "-File"]

        def print_prompt(self):
            return "prompt"

        def quote(self, s):
            """
            Tester will pass strings to native commands on Windows so extra
            parsing rules are used. Check `PowerShellActivator.quote` for more
            details.
            """
            text = PowerShellActivator.quote(s)
            return text.replace('"', '""') if sys.platform == "win32" else text

        def activate_call(self, script):
            # Commands are called without quotes in PowerShell
            cmd = self.activate_cmd
            scr = self.quote(str(script))
            return "{} {}".format(cmd, scr).strip()

    activation_tester(PowerShell)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("it's", id="apostrophe"),
        pytest.param("x\u2019; touch PWNED; \u2018", id="curly-quotes"),
        pytest.param("x\u201a\u201b", id="low-and-reversed-quotes"),
    ],
)
def test_powershell_quote_doubles_every_single_quote_delimiter(value):
    quoted = PowerShellActivator.quote(value)
    assert quoted[0] == quoted[-1] == "'"
    inner = quoted[1:-1]
    for delimiter in ("'", "\u2018", "\u2019", "\u201a", "\u201b"):
        assert inner.count(delimiter) == 2 * value.count(delimiter)


def test_powershell_prompt_not_inside_expandable_string(tmp_path):
    """The prompt must not be placed inside a double-quoted (expandable) PowerShell string."""
    session = cli_run(
        [ensure_text(str(tmp_path / "env")), "--without-pip", "--activators", "powershell", "--prompt", "$(x)"],
    )
    content = (session.creator.bin_dir / "activate.ps1").read_text(encoding="utf-8")
    assert "\"('$(x)') \"" not in content
    assert "(\"(\" + '$(x)' + \") \" + $previous_prompt_value)" in content


@pytest.mark.skipif(find_executable("pwsh") is None, reason="needs pwsh")
@pytest.mark.parametrize(
    "prompt",
    [
        pytest.param("x$(New-Item PWNED)y", id="subexpression"),
        pytest.param("x\u2019; New-Item PWNED; \u2018y", id="curly-quote-breakout"),
    ],
)
def test_powershell_prompt_does_not_run_commands(tmp_path, prompt):
    session = cli_run(
        [ensure_text(str(tmp_path / "env")), "--without-pip", "--activators", "powershell", "--prompt", prompt],
    )
    work_dir = tmp_path / "workdir"
    work_dir.mkdir()
    script = ". $env:_ACTIVATE_UNDER_TEST; Write-Output (prompt)"
    env = os.environ.copy()
    env[str("_ACTIVATE_UNDER_TEST")] = str(session.creator.bin_dir / "activate.ps1")
    process = subprocess.Popen(
        ["pwsh", "-NoProfile", "-NonInteractive", "-Command", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=ensure_text(str(work_dir)),
        env=env,
    )
    out, err = process.communicate()
    out = out.decode("utf-8")
    assert not (work_dir / "PWNED").exists(), err
    assert "({}) ".format(prompt) in out, (out, err)
