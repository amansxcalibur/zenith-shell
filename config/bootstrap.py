import sys

from config.config import config

from wm import get_wm


def bootstrap(runtime: bool = False, can_edit_user_wm_config: bool = False):
    # zenith owned paths (ConfigManager does it auto during init)
    config._ensure_directories()

    # no reload during install
    get_wm().bootstrap(
        runtime=runtime, can_edit_user_wm_config=can_edit_user_wm_config
    )


if __name__ == "__main__":
    bootstrap(can_edit_user_wm_config="--edit-user-wm-config" in sys.argv)
