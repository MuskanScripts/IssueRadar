"""Core package (code name: issueradar).

The product name shown to users lives in ``brand.json``; see ``issueradar.brand``.
"""

from importlib.metadata import PackageNotFoundError, version

from issueradar.brand import BRAND

try:
    __version__ = version(BRAND.distribution)
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
