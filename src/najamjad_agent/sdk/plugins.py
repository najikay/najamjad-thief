"""Loading a replacement component named in configuration (T-2227).

The architecture already depends on protocols rather than classes — `Brain`,
`Speaker`, `Transport` and `Provider` in `domain/ports.py` and `llm/base.py` —
so swapping an implementation is a wiring change, not a code change. This module
is the wiring: it turns a `"package.module:Attribute"` string from a config file
into the object itself.

Deliberately small and deliberately strict. A plugin path that does not resolve
must fail at *load*, with the offending string quoted, rather than at the first
turn of a match — the Assignment 6 failure mode this project exists to avoid was
a config value that named something that did not exist and was only discovered
under time pressure.

Nothing here executes arbitrary code that the *opponent* controls: plugin paths
come from our own local config file, which never crosses the network.
"""

from __future__ import annotations

import importlib
from typing import Any


class PluginError(ValueError):
    """A configured plugin path could not be resolved to an object."""


def load_plugin(path: str) -> Any:
    """Resolve `"module.path:Attribute"` to the attribute itself.

    The colon is required rather than inferred from the last dot: a module and
    a class are different things, and guessing which one `a.b.c` means is how a
    typo silently becomes a different object.
    """
    if ":" not in path:
        raise PluginError(
            f"plugin path {path!r} must be 'module.path:Attribute' — the colon separates "
            "the module from the name inside it"
        )
    module_name, _, attribute = path.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        raise PluginError(f"plugin path {path!r}: cannot import {module_name!r} ({error})") from error
    try:
        return getattr(module, attribute)
    except AttributeError as error:
        raise PluginError(
            f"plugin path {path!r}: {module_name!r} has no attribute {attribute!r}"
        ) from error


def resolve(path: str | None, default: Any) -> Any:
    """The configured plugin, or the default when nothing is configured."""
    return load_plugin(path) if path else default
