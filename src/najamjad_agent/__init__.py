"""NajAmjad agent — P2P cops-and-thieves player (symmetric cop/thief core).

This package is mirrored byte-identically between the `najamjad-cop` and
`najamjad-thief` repositories (PLAN ADR-002); role differences live only in
configuration and strategy selection, never in shared core modules.
"""

from .shared.version import CODE_VERSION

__version__ = CODE_VERSION
__all__ = ["__version__"]
