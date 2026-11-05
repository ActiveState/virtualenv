from __future__ import absolute_import, unicode_literals

import os
import sys
from shutil import copy2

import pytest

from virtualenv.run import cli_run
from virtualenv.seed.embed.pip_invoke import PipInvoke
from virtualenv.seed.wheels.bundle import load_embed_wheel
from virtualenv.seed.wheels.embed import BUNDLE_FOLDER, BUNDLE_SUPPORT
from virtualenv.seed.wheels.util import Wheel
from virtualenv.util.path import Path


@pytest.mark.slow
@pytest.mark.parametrize("no", ["pip", "setuptools", "wheel", ""])
def test_base_bootstrap_via_pip_invoke(tmp_path, coverage_env, mocker, current_fastest, no):
    extra_search_dir = tmp_path / "extra"
    extra_search_dir.mkdir()
    for_py_version = "{}.{}".format(*sys.version_info[0:2])
    new = BUNDLE_SUPPORT[for_py_version]
    for wheel_filename in BUNDLE_SUPPORT[for_py_version].values():
        copy2(str(BUNDLE_FOLDER / wheel_filename), str(extra_search_dir))

    def _load_embed_wheel(app_data, distribution, for_py_version, version):
        return load_embed_wheel(app_data, distribution, old_ver, version)

    old_ver = "2.7"
    old = BUNDLE_SUPPORT[old_ver]
    mocker.patch("virtualenv.seed.wheels.bundle.load_embed_wheel", side_effect=_load_embed_wheel)

    def _execute(cmd, env):
        expected = set()
        for distribution, with_version in versions.items():
            if distribution == no:
                continue
            if with_version == "embed" or old[distribution] == new[distribution]:
                expected.add(BUNDLE_SUPPORT[old_ver][distribution])
            else:
                expected.add(new[distribution])
        # pip must never consult an index, only a private folder holding exactly the selected wheels
        assert "--no-index" in cmd
        assert "--no-deps" in cmd
        assert cmd.count("--find-links") == 1
        folder = Path(cmd[cmd.index("--find-links") + 1])
        assert folder not in (BUNDLE_FOLDER, extra_search_dir)
        assert {i.name for i in folder.iterdir()} == expected
        return original(cmd, env)

    original = PipInvoke._execute
    run = mocker.patch.object(PipInvoke, "_execute", side_effect=_execute)
    # "bundle" with --download would now download (and verify) through virtualenv, so stay offline with local versions
    versions = {"pip": "embed", "setuptools": "embed", "wheel": new["wheel"].split("-")[1]}

    create_cmd = [
        "--seeder",
        "pip",
        str(tmp_path / "env"),
        "--download",
        "--creator",
        current_fastest,
        "--extra-search-dir",
        str(extra_search_dir),
        "--app-data",
        str(tmp_path / "app-data"),
    ]
    for dist, version in versions.items():
        create_cmd.extend(["--{}".format(dist), version])
    if no:
        create_cmd.append("--no-{}".format(no))
    result = cli_run(create_cmd)
    coverage_env()

    assert result
    assert run.call_count == 1

    site_package = result.creator.purelib
    pip = site_package / "pip"
    setuptools = site_package / "setuptools"
    wheel = site_package / "wheel"
    files_post_first_create = list(site_package.iterdir())

    if no:
        no_file = locals()[no]
        assert no not in files_post_first_create

    for key in ("pip", "setuptools", "wheel"):
        if key == no:
            continue
        assert locals()[key] in files_post_first_create


def test_pip_invoke_installs_only_selected_wheels(tmp_path, mocker):
    """the pip seeder obtains (and so verifies) downloads itself; pip only sees a private copy of the selected wheels"""
    selected = {dist: Wheel(BUNDLE_FOLDER / name) for dist, name in BUNDLE_SUPPORT["2.7"].items()}
    get_wheel = mocker.patch(
        "virtualenv.seed.embed.pip_invoke.get_wheel",
        side_effect=lambda distribution, **kwargs: selected[distribution],
    )
    seeder = PipInvoke.__new__(PipInvoke)
    seeder.download = True
    seeder.extra_search_dir = [BUNDLE_FOLDER]
    seeder.app_data = None
    seeder.periodic_update = False
    seeder.env = {}
    mocker.patch.object(PipInvoke, "distribution_to_versions", return_value={i: "bundle" for i in selected})

    with seeder.get_pip_install_cmd(tmp_path / "python", "2.7") as cmd:
        folder = cmd[cmd.index("--find-links") + 1]
        assert sorted(os.listdir(folder)) == sorted(i.name for i in selected.values())
        assert "--no-index" in cmd
        assert "--no-deps" in cmd
        assert cmd.count("--find-links") == 1
        assert sorted(cmd[-len(selected) :]) == sorted("{}=={}".format(d, w.version) for d, w in selected.items())
    assert not os.path.exists(folder)
    assert {c[1]["download"] for c in get_wheel.call_args_list} == {True}
