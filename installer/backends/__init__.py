def load_backend(name: str):
    if name == "arch":
        from installer.backends.arch import ArchBackend

        return ArchBackend()
    from installer.backends.ubuntu import UbuntuBackend

    return UbuntuBackend()
