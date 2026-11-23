from config.config import config

from wm import get_wm


def bootstrap(runtime: bool = False):
    # zenith owned paths (ConfigManager does it auto during init)
    config._ensure_directories()

    # no reload during install
    get_wm().bootstrap(runtime=runtime)


if __name__ == "__main__":
    bootstrap()
