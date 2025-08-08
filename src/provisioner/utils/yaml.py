from __future__ import annotations

import pathlib
from typing import Any

import yaml

try:
    from yaml import CDumper as Dumper
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    # we don't NEED cython ext but it's faster so use it if avail.
    from yaml import Dumper, SafeLoader


def pathlib_repr(dumper, data: pathlib.Path):
    return dumper.represent_str(str(data))


def set_repr(dumper, data: set):
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data)


yaml.add_representer(pathlib.PosixPath, pathlib_repr, Dumper=Dumper)
yaml.add_representer(set, set_repr, Dumper=Dumper)


def yaml_dump(data: Any) -> str:
    """YAML textual representation of data"""
    return yaml.dump(data, Dumper=Dumper, explicit_start=True, sort_keys=False)


def yaml_load(*args, **kwargs) -> Any:
    return yaml.load(*args, **kwargs, Loader=SafeLoader)
