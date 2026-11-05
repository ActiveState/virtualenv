from __future__ import absolute_import, unicode_literals

import os
import subprocess
import sys
from distutils.spawn import find_executable

import pytest

from virtualenv.activation import BashActivator
from virtualenv.info import IS_WIN
from virtualenv.util.six import ensure_text


def _bash_version():
    bash = find_executable("bash")
    if bash is None:
        return None
    out = subprocess.check_output([bash, "-c", 'printf "%s" "$((BASH_VERSINFO[0] * 100 + BASH_VERSINFO[1]))"'])
    return int(out.decode("ascii"))


def _run(cmd, cwd=None, env=None, stdin=None):
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
    )
    out, err = process.communicate(stdin.encode("utf-8") if stdin is not None else None)
    return process.returncode, out.decode("utf-8"), err.decode("utf-8")


def _create(dest, prompt, current_fastest):
    args = [dest, "--without-pip", "--creator", current_fastest, "--no-periodic-update"]
    args += ["--activators", "bash"]
    if prompt is not None:
        args += ["--prompt", prompt]
    # create in a fresh interpreter: tests/unit/create/.../testing/path.py sets a "\\" altsep on the shared POSIX path
    # flavour at import time, which would turn the backslashes of some directory names here into separators in-process
    subprocess.check_call([sys.executable, "-m", "virtualenv"] + args)
    return os.path.join(dest, "Scripts" if IS_WIN else "bin")


@pytest.mark.skipif(IS_WIN, reason="Github Actions ships with WSL bash")
def test_bash(raise_on_non_source_class, activation_tester):
    class Bash(raise_on_non_source_class):
        def __init__(self, session):
            super(Bash, self).__init__(
                BashActivator,
                session,
                "bash",
                "activate",
                "sh",
                "You must source this script: $ source ",
            )

        def print_prompt(self):
            # render PS1 the way bash draws it before each interactive command
            return 'printf "%s\\n" "${PS1@P}"'

    if _bash_version() < 404:
        pytest.skip("${PS1@P} needs bash 4.4 or later")
    activation_tester(Bash)


@pytest.fixture(params=["bash", "zsh"])
def prompt_after_activate(request, tmp_path, current_fastest):
    shell = request.param
    if find_executable(shell) is None:
        pytest.skip("{} is not installed".format(shell))
    if shell == "bash" and _bash_version() < 404:
        pytest.skip("${PS1@P} needs bash 4.4 or later")

    def build(prompt, env_name, extra_env=None):
        # a plain string path: tests/unit/create/.../testing/path.py sets a "\\" altsep on the shared POSIX path
        # flavour at import time, which would turn backslashes in env_name into separators in Path objects
        bin_dir = _create(os.path.join(ensure_text(str(tmp_path)), env_name), prompt, current_fastest)
        work_dir = tmp_path / "workdir"
        if not work_dir.exists():
            work_dir.mkdir()
        # the path is passed as $1 so the outer shell cannot expand a payload dir name while locating the script;
        # ${PS1@P} renders the prompt exactly as bash does before each interactive command, and in zsh (e) applies
        # what PROMPT_SUBST does at each draw before (%) expands the prompt escapes
        render = {
            "bash": ["bash", "--norc", "--noprofile", "-c", 'source "$1"; printf "%s" "${PS1@P}"'],
            "zsh": ["zsh", "-f", "-c", 'setopt prompt_subst; source "$1"; print -rn -- "${(%)${(e)PS1}}"'],
        }[shell]
        env = os.environ.copy()
        env.pop(str("PS1"), None)
        env.pop(str("VIRTUAL_ENV_DISABLE_PROMPT"), None)
        env.update(extra_env or {})
        cmd = render + [shell, os.path.join(bin_dir, "activate")]
        _, out, _ = _run(cmd, cwd=ensure_text(str(work_dir)), env=env)
        return work_dir, out

    return build


@pytest.mark.skipif(IS_WIN, reason="Github Actions ships with WSL bash")
@pytest.mark.parametrize(
    "prompt, env_name",
    [
        pytest.param("x$(touch PWNED)y", "env", id="prompt-command-substitution"),
        pytest.param("x`touch PWNED`y", "env", id="prompt-backticks"),
        pytest.param("x${$(touch PWNED)}y", "env", id="prompt-parameter-expansion"),
        pytest.param("x\\$(touch PWNED)y", "env", id="prompt-backslash-command-substitution"),
        pytest.param("x\\`touch PWNED`y", "env", id="prompt-backslash-backticks"),
        pytest.param(None, "x$(touch PWNED)y", id="dirname-command-substitution"),
        pytest.param(None, "x\\$(touch PWNED)y", id="dirname-backslash-command-substitution"),
        pytest.param(None, "x`touch PWNED`y", id="dirname-backticks"),
        pytest.param(None, "A__VIRTUAL_NAME__B/x'$(touch PWNED)'y", id="placeholder-in-parent-dir"),
        pytest.param(None, "A__BIN_NAME__B/x'$(touch PWNED)'y", id="bin-placeholder-in-parent-dir"),
    ],
)
def test_prompt_does_not_run_commands(prompt_after_activate, prompt, env_name):
    """GHSA-5vjq-rrrf-7h2q (zsh PROMPT_SUBST) and GHSA-vxj4-q4g9-crj7 (backslash before $)."""
    work_dir, _ = prompt_after_activate(prompt, env_name)

    assert not (work_dir / "PWNED").exists()


@pytest.mark.skipif(IS_WIN, reason="Github Actions ships with WSL bash")
@pytest.mark.parametrize(
    "prompt",
    [
        pytest.param("myenv", id="plain"),
        pytest.param("a%n$HOME\\b`c`", id="special-characters"),
        pytest.param("a\\$HOME", id="backslash-before-dollar"),
        pytest.param("a\\`c`", id="backslash-before-backtick"),
        pytest.param("x\\\\y", id="doubled-backslash"),
        pytest.param("e\\", id="trailing-backslash"),
    ],
)
@pytest.mark.parametrize("compatibility", [pytest.param("42", id="bash42"), pytest.param("51", id="bash51")])
def test_prompt_renders_name_literally(prompt_after_activate, prompt, compatibility):
    """GHSA-6w3r-xr62-4xcp: older BASH_COMPAT modes must not change how the prompt value is read."""
    _, rendered = prompt_after_activate(prompt, "env", {str("BASH_COMPAT"): str(compatibility)})

    assert rendered.startswith("({}) ".format(prompt)), rendered


@pytest.mark.skipif(IS_WIN or find_executable("bash") is None, reason="requires POSIX bash")
@pytest.mark.parametrize(
    "before, after, expected",
    [
        pytest.param("shopt -u promptvars", "", "(x$(touch PWNED)y) __END__", id="promptvars-disabled"),
        pytest.param(
            "shopt -u promptvars; set -o posix",
            "",
            "(x$(touch PWNED)y) __END__",
            id="promptvars-disabled-posix",
        ),
        pytest.param("", "set -u; unset VIRTUAL_ENV_PROMPT", "() __END__", id="unset-with-nounset"),
    ],
)
def test_bash_prompt_options(tmp_path, current_fastest, before, after, expected):
    """GHSA-6w3r-xr62-4xcp: the prompt stays literal whichever prompt options the user's bash has."""
    bin_dir = _create(os.path.join(ensure_text(str(tmp_path)), "env"), "x$(touch PWNED)y", current_fastest)
    activate = BashActivator.quote(os.path.join(bin_dir, "activate"))
    script = "{}\nPS1=__END__\n. {}\n{}\nexit\n".format(before, activate, after)
    env = os.environ.copy()
    env.pop(str("VIRTUAL_ENV_DISABLE_PROMPT"), None)
    _, _, err = _run(["bash", "--noprofile", "--norc", "-i"], cwd=ensure_text(str(tmp_path)), env=env, stdin=script)
    assert expected in err, err
    assert "unbound variable" not in err, err
    assert not (tmp_path / "PWNED").exists()


@pytest.mark.skipif(IS_WIN or find_executable("dash") is None, reason="needs dash as a POSIX shell")
def test_bash_activate_sources_under_dash(tmp_path, current_fastest):
    dest = os.path.join(ensure_text(str(tmp_path)), "env")
    bin_dir = _create(dest, None, current_fastest)
    cmd = [
        "dash",
        "-c",
        'PS1="base "; . "$1" && printf "%s|%s|%s" "$VIRTUAL_ENV" "$PS1" "$VIRTUAL_ENV_PROMPT"',
        "dash",
        os.path.join(bin_dir, "activate"),
    ]
    code, out, err = _run(cmd)
    assert (code, out) == (0, "{}|base |env".format(dest)), err
