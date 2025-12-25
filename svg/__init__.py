from typing import TYPE_CHECKING

from . import svg

for mod in [svg]:
    for name in dir(mod):
        if not name.startswith("__"):
            globals()[name] = getattr(mod, name)

if TYPE_CHECKING:
    from .svg import *
