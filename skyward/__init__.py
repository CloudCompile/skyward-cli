"""skyward — Skyward Student/Family Access from the terminal."""

__version__ = "0.1.0"

from .client import (  # noqa: F401
    Credentials,
    LoginError,
    SessionExpired,
    SkywardClient,
    SkywardError,
    load_config,
    resolve_credentials,
)
