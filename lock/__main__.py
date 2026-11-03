import sys

from config.info import IS_WAYLAND


def main() -> int:
    if "--child" in sys.argv[1:]:
        if IS_WAYLAND:
            from .wayland import run
        else:
            from .x11 import run

        return run()

    from .supervisor import supervise

    # -f / --daemonize: return once locked, like swaylock -f
    daemonize = any(arg in ("-f", "--daemonize") for arg in sys.argv[1:])
    return supervise(daemonize=daemonize)


if __name__ == "__main__":
    sys.exit(main())
