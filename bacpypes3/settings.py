"""
Settings
"""

import os

from typing import Any, Dict


class Settings(Dict[str, Any]):
    """
    Settings
    """

    def __getattr__(self, name: str) -> Any:
        if name not in self:
            raise AttributeError("No such setting: " + name)
        return self[name]

    def __setattr__(self, name: str, value: Any) -> None:
        if name not in self:
            raise AttributeError("No such setting: " + name)
        self[name] = value


# globals
settings = Settings(
    debug=[],
    color=False,
    debug_file="",
    max_bytes=1048576,
    backup_count=5,
    route_aware=False,
    cov_lifetime=60,
    config={},
)


def os_settings() -> None:
    """
    Update the settings from known OS environment variables.
    """
    for setting_name, env_name in (
        ("debug", "BACPYPES_DEBUG"),
        ("color", "BACPYPES_COLOR"),
        ("debug_file", "BACPYPES_DEBUG_FILE"),
        ("max_bytes", "BACPYPES_MAX_BYTES"),
        ("backup_count", "BACPYPES_BACKUP_COUNT"),
        ("route_aware", "BACPYPES_ROUTE_AWARE"),
        ("cov_lifetime", "BACPYPES_COV_LIFETIME"),
    ):
        env_value = os.getenv(env_name, None)
        if env_value is not None:
            cur_value = settings[setting_name]

            setting_value: Any
            if isinstance(cur_value, bool):
                env_value = env_value.lower()
                if env_value in ("set", "true"):
                    setting_value = True
                elif env_value in ("reset", "false"):
                    setting_value = False
                else:
                    raise ValueError("setting: " + setting_name)
            elif isinstance(cur_value, int):
                try:
                    setting_value = int(env_value)
                except Exception:
                    raise ValueError("setting: " + setting_name)
            elif isinstance(cur_value, str):
                setting_value = env_value
            elif isinstance(cur_value, list):
                setting_value = env_value.split()
            elif isinstance(cur_value, set):
                setting_value = set(env_value.split())
            else:
                raise TypeError("setting type: " + setting_name)

            settings[setting_name] = setting_value


def dict_settings(**kwargs: Any) -> None:
    """
    Update the settings from key/value content.  Lists are morphed into sets
    if necessary, giving a setting any value is acceptable if there isn't one
    already set, otherwise protect against setting type changes.
    """
    for setting_name, kw_value in kwargs.items():
        cur_value = settings.get(setting_name, None)

        if cur_value is None:
            pass
        if isinstance(cur_value, bool):
            if isinstance(kw_value, bool):
                pass
            elif isinstance(kw_value, int):
                kw_value = bool(kw_value)
            elif isinstance(kw_value, str):
                kw_value = kw_value.lower()
                if kw_value in ("set", "true"):
                    kw_value = True
                elif kw_value in ("reset", "false"):
                    kw_value = False
                else:
                    raise ValueError("setting: " + setting_name)
        elif isinstance(cur_value, int):
            if isinstance(kw_value, int):
                pass
            elif isinstance(kw_value, str):
                kw_value = int(kw_value)
            else:
                raise ValueError("setting: " + setting_name)
        elif isinstance(cur_value, set):
            if isinstance(kw_value, list):
                kw_value = set(kw_value)
            elif not isinstance(kw_value, set):
                raise TypeError(setting_name)
        elif not isinstance(kw_value, type(cur_value)):
            raise TypeError("setting type: " + setting_name)
        settings[setting_name] = kw_value
