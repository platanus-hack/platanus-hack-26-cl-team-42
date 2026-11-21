import inspect
import os
import warnings
from collections import namedtuple
from itertools import chain
from typing import Any, Generator

from decouple import config
from pydantic import BaseModel

REQUIRE_SECURE_VAR = 'UNCOUPLE_REQUIRE_SECURE'


class InsecureDefaultWarning(UserWarning):
    """Emitted when an :class:`InsecureDefault` fallback is used."""


class InsecureDefault:
    """Marker for a fallback that is acceptable for local development only.

    Declare a field as ``SECRET_KEY: str = InsecureDefault("test")`` to provide a
    working default when the environment variable is unset. Whenever the fallback
    is used a warning is logged. If the ``UNCOUPLE_REQUIRE_SECURE`` environment
    variable is truthy, relying on the fallback is a fatal error instead, forcing
    the value to be supplied explicitly (e.g. in production).
    """

    def __init__(self, value: Any):
        self.value = value

    def __repr__(self) -> str:
        return f'InsecureDefault({self.value!r})'


class InsecureConfigError(Exception):
    """Raised when insecure defaults are used while secure config is required."""

    def __init__(self, keys: list[str]):
        self.keys = keys
        super().__init__(
            f'{REQUIRE_SECURE_VAR} is set but insecure default(s) would be used '
            f'for: {", ".join(keys)}. Provide explicit values via the environment.'
        )


class Config(BaseModel):
    """Extend with type annotations to load configuration from environment variables."""

    @classmethod
    def load(cls, prefix: str = '', **defaults):
        """Load configuration from environment variables."""
        insecure: list[str] = []
        loaded_items = _nested_dict(_gen_loaded_items(prefix, cls, defaults, insecure))

        if insecure:
            if config(REQUIRE_SECURE_VAR, default=False, cast=bool):
                raise InsecureConfigError(insecure)
            for key in insecure:
                warnings.warn(
                    f'Using insecure default for {key}; set it in the '
                    'environment before deploying.',
                    InsecureDefaultWarning,
                    stacklevel=2,
                )

        return cls(**(defaults | loaded_items))

    @staticmethod
    def find():
        """Iterate all avaialble config parameters.

        Include from both environment and decouple's loaded repository.
        """
        return iter(
            {
                key: value
                for key, value in chain(
                    os.environ.items(),
                    config.config.repository.data.items(),
                )
            }
        )


def _gen_loaded_items(
    prefix: str, cls: type(Config), defaults: dict[str, Any], insecure: list[str]
) -> Generator[[str, Any], None, None]:
    """Generate loaded items from the given Config class.

    ``insecure`` is appended with the full config key of any field that resolved
    to its :class:`InsecureDefault` fallback (i.e. the environment did not
    provide a value).
    """
    prefix_keys = [prefix] if prefix else []

    stack_item = namedtuple('stack_item', 'keys cls')
    stack = [stack_item(keys=[], cls=cls)]

    while stack:
        item = stack.pop()
        for _param, _type in inspect.signature(item.cls).parameters.items():
            # Resolve value to:
            # 1. Envvar or .env file (via decouple)
            # 2. Otherwise, explicitly passed kwarg in load()
            # 3. Otherwise, default as configured in the Config class
            # 4. Final fallback value will be `empty` if no default was
            #    specified in 3, in which case the param is omitted
            item_keys = [*item.keys, _param]
            config_key = '_'.join((*prefix_keys, *item_keys))
            value = config(config_key, default=defaults.get(_param, _type.default))

            # An InsecureDefault only survives when the environment provided
            # nothing, so unwrap it to its real value and flag the key.
            if isinstance(value, InsecureDefault):
                insecure.append(config_key)
                value = value.value

            if value != _type.empty:
                yield item_keys, value

            if inspect.isclass(_type.annotation):
                if issubclass(_type.annotation, Config):
                    stack.append(stack_item(item_keys, _type.annotation))


def _nested_dict(pairs: list[tuple[list[str], Any]]) -> dict:
    """Build a nested dictionary from an iterable of (keys: list[str], value: Any).

    The first element of each pair is a list of keys, and the second element is
    the value.
    """
    nested = {}
    for keys, value in pairs:
        cursor = nested
        for key in keys[:-1]:
            cursor = cursor.setdefault(key, {})
        cursor[keys[-1]] = value
    return nested
