import os

from setuptools import __version__, setup

# ActiveState security release on the 20.15.1.x maintenance line. The version is pinned here rather than derived from
# the nearest git tag so that every build of this branch (sdist, wheel, or an untagged checkout) reports the same
# PEP 440 version. An explicit SETUPTOOLS_SCM_PRETEND_VERSION still wins.
os.environ.setdefault("SETUPTOOLS_SCM_PRETEND_VERSION", "20.15.1.post3")

if int(__version__.split(".")[0]) < 41:
    raise RuntimeError("setuptools >= 41 required to build")

setup(
    use_scm_version={
        "write_to": "src/virtualenv/version.py",
        "write_to_template": 'from __future__ import  unicode_literals\n\n__version__ = "{version}"\n',
    },
    setup_requires=["setuptools_scm >= 2"],
)
