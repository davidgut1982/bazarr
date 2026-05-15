# coding=utf-8

import importlib
import importlib.util
from importlib import metadata
import logging
import os
from pathlib import Path
import re
import subprocess
import sys

from literals import ENV_RESTARTFILE, EXIT_NORMAL, EXIT_REQUIREMENTS_ERROR


RUNTIME_IMPORTS = (
    "setuptools",
    "signalrcore",
    "subliminal",
    "flask_compress",
    "py7zr",
    "deathbycaptcha",
    "click_option_group",
    "tomlkit",
    "msgpack",
    "aiohttp",
    "cachetools",
    "lxml",
    "numpy",
    "webrtcvad",
    "PIL",
    "cryptography",
    "jwt",
    "yaml",
    "rarfile",
)

WINDOWS_RUNTIME_IMPORTS = (
    "win32api",
    "win32con",
)

RUNTIME_REQUIREMENTS = {
    "setuptools": ("setuptools", ">=82.0.1"),
    "signalrcore": ("signalrcore", "==0.9.71"),
    "subliminal": ("subliminal", "==2.6.0"),
    "flask_compress": ("Flask-Compress", "==1.24"),
    "py7zr": ("py7zr", "==1.1.0"),
    "deathbycaptcha": ("deathbycaptcha-official", "==4.7.1"),
    "click_option_group": ("click-option-group", ">=0.5.6"),
    "tomlkit": ("tomlkit", ">=0.13.2"),
    "msgpack": ("msgpack", "==1.0.2"),
    "aiohttp": ("aiohttp", ">=3.13.5"),
    "cachetools": ("cachetools", ">=7.1.1"),
    "lxml": ("lxml", ">=6.1.0"),
    "numpy": ("numpy", ">=2.0.0,<2.4.0"),
    "webrtcvad": ("webrtcvad-wheels", ">=2.0.14"),
    "PIL": ("Pillow", ">=12.2.0"),
    "cryptography": ("cryptography", ">=48.0.0"),
    "jwt": ("PyJWT", ">=2.12.1"),
    "yaml": ("PyYAML", ">=6.0.3"),
}

WINDOWS_RUNTIME_REQUIREMENTS = {
    "win32api": ("pywin32", ">=311"),
    "win32con": ("pywin32", ">=311"),
}

REPO_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_RUNTIME_ORIGINS = (
    REPO_ROOT / "libs",
    REPO_ROOT / "custom_libs",
)

UNVENDORED_RUNTIME_IMPORTS = {
    "signalrcore",
    "subliminal",
    "flask_compress",
    "py7zr",
    "deathbycaptcha",
    "click_option_group",
    "tomlkit",
    "msgpack",
    "yaml",
}


def is_virtualenv():
    base_prefix = getattr(sys, "base_prefix", None)
    real_prefix = getattr(sys, "real_prefix", None) or sys.prefix
    return base_prefix != real_prefix


def _version_tuple(version):
    parts = re.findall(r"\d+", version.split("+", 1)[0].split("-", 1)[0])
    return tuple(int(part) for part in parts)


def _satisfies_spec(installed_version, spec):
    installed = _version_tuple(installed_version)
    for item in spec.split(","):
        item = item.strip()
        if item.startswith("=="):
            if installed != _version_tuple(item[2:]):
                return False
        elif item.startswith(">="):
            if installed < _version_tuple(item[2:]):
                return False
        elif item.startswith("<"):
            if installed >= _version_tuple(item[1:]):
                return False
        else:
            raise ValueError(f"Unsupported requirement specifier: {item}")
    return True


def _module_origin(module):
    spec = importlib.util.find_spec(module)
    if not spec or not spec.origin or spec.origin in ("built-in", "frozen"):
        return None
    return Path(spec.origin).resolve()


def _has_forbidden_origin(module):
    origin = _module_origin(module)
    if not origin:
        return False
    return any(origin.is_relative_to(path) for path in FORBIDDEN_RUNTIME_ORIGINS)


def _requirement_is_satisfied(distribution, spec):
    try:
        installed_version = metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return False
    return _satisfies_spec(installed_version, spec)


def missing_runtime_requirements():
    missing = set()
    probes = list(RUNTIME_IMPORTS)
    requirements = dict(RUNTIME_REQUIREMENTS)
    if os.name == "nt":
        probes.extend(WINDOWS_RUNTIME_IMPORTS)
        requirements.update(WINDOWS_RUNTIME_REQUIREMENTS)

    for module in probes:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.add(module)
            continue

        if module in UNVENDORED_RUNTIME_IMPORTS and _has_forbidden_origin(module):
            missing.add(module)
            continue

        requirement = requirements.get(module)
        if requirement and not _requirement_is_satisfied(*requirement):
            missing.add(module)

    return sorted(missing)


def install_requirements(missing_modules=None):
    if importlib.util.find_spec("pip") is None:
        logging.info("BAZARR unable to install requirements because pip is not installed.")
        return False

    if os.path.expanduser("~") == "/":
        logging.info("BAZARR unable to install requirements because the user has no home directory.")
        return False

    logging.info("BAZARR installing requirements. Missing imports: %s", ", ".join(missing_modules or []))

    pip_command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "-qq",
        "--disable-pip-version-check",
        "-r",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "requirements.txt"),
    ]
    if not is_virtualenv():
        pip_command.insert(4, "--user")

    try:
        subprocess.check_output(pip_command, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logging.exception("BAZARR requirements.txt installation result: %s", e.stdout)
        os._exit(EXIT_REQUIREMENTS_ERROR)

    logging.info("BAZARR requirements installed.")
    return True


def restart_after_requirements_install():
    restart_file = os.environ.get(ENV_RESTARTFILE)
    if restart_file:
        try:
            Path(restart_file).touch()
        except Exception:
            logging.exception("BAZARR cannot create restart file after installing requirements.")
        else:
            os._exit(EXIT_NORMAL)

    os.execv(sys.executable, [sys.executable] + sys.argv)


def ensure_requirements(no_update=False):
    if no_update:
        return False

    missing = missing_runtime_requirements()
    if not missing:
        return False

    if install_requirements(missing):
        restart_after_requirements_install()

    return True
