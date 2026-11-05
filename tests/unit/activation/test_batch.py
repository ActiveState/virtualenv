from __future__ import absolute_import, unicode_literals

import logging
from argparse import Namespace

import pytest

from virtualenv.activation import BatchActivator


def test_batch(activation_tester_class, activation_tester, tmp_path, activation_python):
    version_script = tmp_path / "version.bat"
    version_script.write_text("ver")

    class Batch(activation_tester_class):
        def __init__(self, session):
            super(Batch, self).__init__(BatchActivator, session, None, "activate.bat", "bat")
            self._version_cmd = [str(version_script)]
            self._invoke_script = []
            self.deactivate = "call deactivate"
            self.activate_cmd = "call"
            self.pydoc_call = "call {}".format(self.pydoc_call)
            self.unix_line_ending = False

        def _get_test_lines(self, activate_script):
            # for BATCH utf-8 support need change the character code page to 650001
            return ["@echo off", "", "chcp 65001 1>NUL"] + super(Batch, self)._get_test_lines(activate_script)

        def quote(self, s):
            if '"' in s or " " in s:
                text = s.replace('"', r"\"")
                return '"{}"'.format(text)
            return s

        def print_prompt(self):
            return 'echo "%PROMPT%"'

    activation_tester(Batch)


class _MockInterpreter(object):
    os = "nt"


class _MockCreator(object):
    def __init__(self, dest):
        self.dest = dest
        self.bin_dir = dest / "Scripts"
        self.bin_dir.mkdir(parents=True)
        self.interpreter = _MockInterpreter()
        self.pyenv_cfg = {}
        self.env_name = "test-env"


@pytest.mark.parametrize(
    "value, expected",
    [
        pytest.param("plain", "plain", id="plain"),
        pytest.param('x" & calc & "', "x    calc    ", id="quote-ampersand"),
        pytest.param("a|b<c>d^e!f", "a b c d e f", id="operators"),
        pytest.param("100%PATH%", "100%%PATH%%", id="percent"),
        pytest.param("a\r\n& calc", "a    calc", id="line-break"),
        pytest.param("C:\\Program Files (x86)\\env", "C:\\Program Files (x86)\\env", id="parentheses"),
    ],
)
def test_batch_quote(value, expected):
    """GHSA-x78j-v8h9-3j2q: values inside set "VAR=value" cannot break out into cmd.exe syntax."""
    assert BatchActivator.quote(value) == expected


def test_batch_prompt_cannot_inject_commands(tmp_path):
    creator = _MockCreator(tmp_path / "env")
    activator = BatchActivator(Namespace(prompt='x" & calc & echo "\r\nstart calc'))

    generated = activator.generate(creator)

    assert generated
    content = (creator.bin_dir / "activate.bat").read_text(encoding="utf-8")
    prompt_lines = [line for line in content.splitlines() if "calc" in line]
    assert prompt_lines
    for line in prompt_lines:
        assert "&" not in line, line
        assert line.count('"') % 2 == 0, line
        assert not line.lstrip().startswith("start"), line


def test_batch_skips_destination_with_ampersand(tmp_path, caplog):
    """An `&` in the destination can never be represented, so generation must skip it, not guess."""
    caplog.set_level(logging.WARNING)
    creator = _MockCreator(tmp_path / "weird&dest")
    activator = BatchActivator(Namespace(prompt=None))

    generated = activator.generate(creator)

    assert generated == []
    assert list(creator.bin_dir.iterdir()) == []
    assert "skipping batch activation scripts" in caplog.text
    assert "&" in caplog.text
