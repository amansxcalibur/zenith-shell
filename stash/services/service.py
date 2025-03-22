from fabric.core.service import Service, Signal

class NameService(Service):
    @Signal
    def name_changed(self, new_name: str) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = ""

    def get_name(self) -> str:
        return self.name

    def set_name(self, new_name: str) -> None:
        self.name = new_name

        # Emit the "name-changed" signal
        self.name_changed(new_name)

        # Alternative ways to emit a signal:
        # self.name_changed.emit(new_name)
        # self.emit("name-changed", new_name)

name_service = NameService()

# Connect a listener to the "name-changed" signal
name_service.connect(
    "name-changed",
    lambda self,new_name: print(f"The name has changed, new name is {new_name}")
)

# Alternative way to connect to the signal
# name_service.name_changed.connect(...)

# Trigger the signal by changing the name
name_service.set_name("Homan")
print("hello")