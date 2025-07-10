# todo: integrate with pulsectl

from fabric.core.service import Service, Signal


class VolumeService(Service):

    _instance = None

    @Signal
    def value_changed(self, new_value: int, max_value: int) -> None:...

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_singleton()
        return cls._instance

    def _init_singleton(self):
        super().__init__()