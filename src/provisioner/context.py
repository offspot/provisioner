import logging
import os
from dataclasses import dataclass
from typing import Any

import humanfriendly

from provisioner.__about__ import __version__
from provisioner.constants import NAME, NAME_HUMAN


def set_from_env(name: str) -> set[str]:
    """set() from ENV"""
    return {entry for entry in (os.getenv(name) or "").split("|") if entry}


DEFAULT_DEBUG: bool = bool(os.getenv("DEBUG"))
DEFAULT_FAKE_PI: bool = bool(os.getenv("FAKE_PI"))
DEFAULT_MIN_IMG_SIZE: int = humanfriendly.parse_size(
    os.getenv("MIN_IMG_SIZE") or "300MB"
)
DEFAULT_IS_INTERACTIVE: bool = bool(os.getenv("INTERACTIVE"))

# avoid debug-level logs of 3rd party deps
for module in ("urllib3", "asyncio"):
    logging.getLogger(module).setLevel(logging.INFO)


@dataclass(kw_only=True)
class Context:

    # singleton instance
    _instance: "Context | None" = None

    # debug flag
    debug: bool = DEFAULT_DEBUG
    fake_pi: bool = DEFAULT_FAKE_PI
    interactive: bool = DEFAULT_IS_INTERACTIVE

    min_img_size: int = DEFAULT_MIN_IMG_SIZE

    logger: logging.Logger = logging.getLogger(NAME)  # noqa: RUF009

    @classmethod
    def setup(cls, **kwargs: Any):
        if cls._instance:
            raise OSError("Already inited Context")
        cls._instance = cls(**kwargs)
        cls.setup_logger()

    @classmethod
    def setup_logger(cls):
        debug = cls._instance.debug if cls._instance else cls.debug
        if cls._instance:
            cls._instance.logger.setLevel(logging.DEBUG if debug else logging.INFO)
        else:
            cls.logger.setLevel(logging.DEBUG if debug else logging.INFO)
        logging.basicConfig(
            level=logging.DEBUG if debug else logging.INFO,
            format="%(asctime)s %(levelname)s | %(message)s",
        )
        def handle_exc(msg, *args, **kwargs):
            cls.logger.debug(msg, *args, exc_info=True, **kwargs)
        cls.logger.exception =handle_exc

    @classmethod
    def get(cls) -> "Context":
        if not cls._instance:
            raise OSError("Uninitialized context")  # pragma: no cover
        return cls._instance

    @staticmethod
    def about() -> str:
        return f"{NAME_HUMAN} {__version__}"
