"""revue-portee: scoping reviews (JBI, PRISMA-ScR) with AI as a traceable second reviewer."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("revue-portee")
except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
