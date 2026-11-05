from __future__ import absolute_import, unicode_literals

import hashlib
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime
from subprocess import CalledProcessError

import pytest
from six import StringIO
from six.moves.urllib.error import URLError

from virtualenv.app_data import AppDataDiskFolder
from virtualenv.info import IS_PYPY, PY2
from virtualenv.seed.wheels.acquire import download_wheel, get_wheel, pip_wheel_env_run
from virtualenv.seed.wheels.embed import get_embed_wheel
from virtualenv.seed.wheels.periodic_update import _PYPI_CACHE, UnverifiedWheelError, dump_datetime
from virtualenv.seed.wheels.util import Wheel
from virtualenv.util.path import Path


@pytest.fixture(autouse=True)
def fake_release_date(mocker):
    mocker.patch("virtualenv.seed.wheels.periodic_update.release_date_for_wheel_path", return_value=None)


def test_pip_wheel_env_run_could_not_find(session_app_data, mocker):
    mocker.patch("virtualenv.seed.wheels.acquire.from_bundle", return_value=None)
    with pytest.raises(RuntimeError, match="could not find the embedded pip"):
        pip_wheel_env_run([], session_app_data, os.environ)


@pytest.fixture()
def download_process(mocker, for_py_version):
    """Mock ``pip download`` to write the bundled pip wheel into its ``-d`` folder, and PyPI to vouch for it."""
    wheel = get_embed_wheel("pip", for_py_version)
    payload = bytearray(wheel.path.read_bytes())
    metadata = json.dumps(
        {
            "releases": {
                wheel.version: [
                    {"filename": wheel.name, "digests": {"sha256": hashlib.sha256(bytes(payload)).hexdigest()}},
                ],
            },
        },
    )

    @contextmanager
    def metadata_response(*args, **kwargs):
        yield StringIO(metadata)

    mocker.patch("virtualenv.seed.wheels.periodic_update.urlopen", side_effect=metadata_response)
    mocker.patch("virtualenv.seed.wheels.periodic_update.sleep")

    def downloaded(cmd, **kwargs):
        (Path(cmd[cmd.index("-d") + 1]) / wheel.name).write_bytes(bytes(payload))
        return process.return_value

    process = mocker.patch("virtualenv.seed.wheels.acquire.Popen", side_effect=downloaded)
    process.return_value.communicate.return_value = "progress complete", ""
    process.return_value.returncode = 0
    _PYPI_CACHE.clear()
    yield process, wheel, payload
    _PYPI_CACHE.clear()  # the mocked responses must not leak into later tests


def _default_index_env():
    return {k: v for k, v in os.environ.items() if k not in ("PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_INDEX")}


@pytest.mark.parametrize(
    "version_spec",
    [
        pytest.param(lambda _wheel: None, id="latest"),
        pytest.param(lambda _wheel: "", id="unpinned"),
        pytest.param(lambda wheel: "=={}".format(wheel.version), id="pinned"),
        pytest.param(lambda wheel: "=={}.0".format(wheel.version), id="pinned-trailing-zero"),
        pytest.param(lambda wheel: "<{}".format(wheel.version_tuple[0] + 1), id="below"),
    ],
)
def test_download_wheel_uses_staged_archive(
    download_process, for_py_version, session_app_data, tmp_path, version_spec
):
    _, expected, _ = download_process
    spec = version_spec(expected)
    result = download_wheel("pip", spec, for_py_version, [], session_app_data, tmp_path, _default_index_env())
    assert (result.path, result.path.read_bytes(), list(tmp_path.iterdir())) == (
        tmp_path / expected.name,
        expected.path.read_bytes(),
        [tmp_path / expected.name],
    )


def test_download_wheel_ignores_pip_output_and_cached_files(
    download_process, for_py_version, session_app_data, tmp_path
):
    """pip's ``Saved``/``File was already downloaded`` lines and pre-existing cache entries do not choose the wheel."""
    process, expected, _ = download_process
    planted = tmp_path / "pip-99.0-py2.py3-none-any.whl"
    planted.write_bytes(b"planted")
    process.return_value.communicate.return_value = "File was already downloaded {}".format(planted), ""
    result = download_wheel("pip", None, for_py_version, [], session_app_data, tmp_path, _default_index_env())
    assert result.path == tmp_path / expected.name
    assert sorted(tmp_path.iterdir()) == sorted([planted, tmp_path / expected.name])


def test_download_wheel_not_found_raises(download_process, for_py_version, session_app_data, tmp_path):
    download_process[0].side_effect = None
    with pytest.raises(RuntimeError, match="could not find downloaded wheel"):
        download_wheel("pip", None, for_py_version, [], session_app_data, tmp_path, _default_index_env())
    assert list(tmp_path.iterdir()) == []


@pytest.mark.usefixtures("download_process")
@pytest.mark.parametrize("version_spec", ["==0.0.0", "<1"])
def test_download_wheel_rejects_wrong_version(for_py_version, session_app_data, tmp_path, version_spec):
    with pytest.raises(RuntimeError, match="unexpected downloaded wheel"):
        download_wheel("pip", version_spec, for_py_version, [], session_app_data, tmp_path, _default_index_env())
    assert list(tmp_path.iterdir()) == []


@pytest.mark.usefixtures("download_process")
def test_download_wheel_rejects_wrong_distribution(for_py_version, session_app_data, tmp_path):
    with pytest.raises(RuntimeError, match="unexpected downloaded wheel"):
        download_wheel("setuptools", None, for_py_version, [], session_app_data, tmp_path, _default_index_env())
    assert list(tmp_path.iterdir()) == []


def test_download_wheel_rejects_unsupported_python(mocker, download_process, session_app_data, tmp_path):
    py3_only = get_embed_wheel("pip", "3.7")  # Requires-Python: >=3.7
    process = download_process[0]

    def downloaded(cmd, **kwargs):
        (Path(cmd[cmd.index("-d") + 1]) / py3_only.name).write_bytes(py3_only.path.read_bytes())
        return process.return_value

    process.side_effect = downloaded
    mocker.patch("virtualenv.seed.wheels.acquire.verify_wheel_digest")
    with pytest.raises(RuntimeError, match="does not support Python"):
        download_wheel("pip", None, "2.7", [], session_app_data, tmp_path, _default_index_env())
    assert list(tmp_path.iterdir()) == []


def test_download_fails(download_process, for_py_version, session_app_data, tmp_path):
    download_process[0].return_value.returncode = 7
    download_process[0].return_value.communicate.return_value = "out", "err"
    with pytest.raises(CalledProcessError) as context:
        download_wheel("pip", "==1", for_py_version, [], session_app_data, tmp_path, os.environ)
    exc = context.value
    if sys.version_info < (3, 5):
        assert exc.output == "outerr"
    else:
        assert exc.output == "out"
        assert exc.stderr == "err"
    assert exc.returncode == 7
    staging = exc.cmd[exc.cmd.index("-d") + 1]
    assert Path(staging).parent == tmp_path
    assert exc.cmd == [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--progress-bar",
        "off",
        "--disable-pip-version-check",
        "--only-binary=:all:",
        "--no-deps",
        "--python-version",
        for_py_version,
        "-d",
        staging,
        "pip==1",
    ]
    assert list(tmp_path.iterdir()) == []


def test_download_wheel_keeps_failed_verification_out_of_cache(
    download_process, for_py_version, session_app_data, tmp_path
):
    download_process[2].extend(b"\n")
    with pytest.raises(RuntimeError, match="but PyPI reports"):
        download_wheel("pip", None, for_py_version, [], session_app_data, tmp_path, _default_index_env())
    assert list(tmp_path.iterdir()) == []


def test_download_wheel_keeps_unverifiable_wheel_out_of_cache(
    mocker, download_process, for_py_version, session_app_data, tmp_path
):
    mocker.patch("virtualenv.seed.wheels.periodic_update.urlopen", side_effect=URLError("offline"))
    with pytest.raises(UnverifiedWheelError):
        download_wheel("pip", None, for_py_version, [], session_app_data, tmp_path, _default_index_env())
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("env_var", ["PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_INDEX"])
def test_download_wheel_preserves_custom_index_policy(
    download_process, for_py_version, session_app_data, tmp_path, env_var
):
    """A configured custom index may legitimately serve a same-named wheel PyPI never built."""
    download_process[2].extend(b"\n")
    env = _default_index_env()
    env[str(env_var)] = str("https://index.example/simple")
    result = download_wheel("pip", None, for_py_version, [], session_app_data, tmp_path, env)
    assert result.path.read_bytes() == bytes(download_process[2])


@pytest.fixture
def downloaded_wheel(mocker):
    wheel = Wheel.from_path(Path("setuptools-0.0.0-py2.py3-none-any.whl"))
    yield wheel, mocker.patch("virtualenv.seed.wheels.acquire.download_wheel", return_value=wheel)


@pytest.mark.parametrize("version", ["bundle", "0.0.0"])
def test_get_wheel_download_called(mocker, for_py_version, session_app_data, downloaded_wheel, version):
    distribution = "setuptools"
    write = mocker.patch("virtualenv.app_data.via_disk_folder.JSONStoreDisk.write")
    wheel = get_wheel(distribution, version, for_py_version, [], True, session_app_data, False, os.environ)
    assert wheel is not None
    assert wheel.name == downloaded_wheel[0].name
    assert downloaded_wheel[1].call_count == 1
    assert write.call_count == 1


@pytest.mark.parametrize("version", ["embed", "pinned"])
def test_get_wheel_download_not_called(mocker, for_py_version, session_app_data, downloaded_wheel, version):
    distribution = "setuptools"
    expected = get_embed_wheel(distribution, for_py_version)
    if version == "pinned":
        version = expected.version
    write = mocker.patch("virtualenv.app_data.via_disk_folder.JSONStoreDisk.write")
    wheel = get_wheel(distribution, version, for_py_version, [], True, session_app_data, False, os.environ)
    assert wheel is not None
    assert wheel.name == expected.name
    assert downloaded_wheel[1].call_count == 0
    assert write.call_count == 0


def test_get_wheel_falls_back_to_bundle_when_unverified(mocker, for_py_version, session_app_data):
    mocker.patch("virtualenv.seed.wheels.acquire.download_wheel", side_effect=UnverifiedWheelError("refusing"))

    wheel = get_wheel("setuptools", "bundle", for_py_version, [], True, session_app_data, False, os.environ)

    assert wheel is not None
    assert wheel.name == get_embed_wheel("setuptools", for_py_version).name


def test_get_wheel_unverified_pinned_version_fails(mocker, for_py_version, session_app_data):
    mocker.patch("virtualenv.seed.wheels.acquire.download_wheel", side_effect=UnverifiedWheelError("refusing"))

    with pytest.raises(UnverifiedWheelError, match="refusing"):
        get_wheel("setuptools", "0.0.0", for_py_version, [], True, session_app_data, False, os.environ)


@pytest.mark.skipif(IS_PYPY and PY2, reason="mocker.spy failing on PyPy 2.x")
def test_get_wheel_download_cached(tmp_path, freezer, mocker, for_py_version, downloaded_wheel):
    from virtualenv.app_data.via_disk_folder import JSONStoreDisk

    app_data = AppDataDiskFolder(folder=str(tmp_path))
    expected = downloaded_wheel[0]
    write = mocker.spy(JSONStoreDisk, "write")
    # 1st call, not cached, download is called
    wheel = get_wheel(expected.distribution, expected.version, for_py_version, [], True, app_data, False, os.environ)
    assert wheel is not None
    assert wheel.name == expected.name
    assert downloaded_wheel[1].call_count == 1
    assert write.call_count == 1
    # 2nd call, cached, download is not called
    wheel = get_wheel(expected.distribution, expected.version, for_py_version, [], True, app_data, False, os.environ)
    assert wheel is not None
    assert wheel.name == expected.name
    assert downloaded_wheel[1].call_count == 1
    assert write.call_count == 1
    wrote_json = write.call_args[0][1]
    assert wrote_json == {
        "completed": None,
        "periodic": None,
        "started": None,
        "versions": [
            {
                "filename": expected.name,
                "release_date": None,
                "found_date": dump_datetime(datetime.now()),
                "source": "download",
            },
        ],
    }
