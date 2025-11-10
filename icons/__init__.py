from typing import TYPE_CHECKING

from . import icons_nerd, icons_material, svg

for mod in [icons_nerd, icons_material, svg]:
    for name in dir(mod):
        if not name.startswith("__"):
            globals()[name] = getattr(mod, name)

if TYPE_CHECKING:
    from .icons_nerd import *
    from .icons_material import *
    from .svg import *
