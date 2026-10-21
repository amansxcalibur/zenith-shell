from services.theme import ThemeMode, ThemeService


def hex_to_rgb01(hex_color):
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return r, g, b


def get_css_variable(file_path, var_name):
    with open(file_path) as f:
        for line in f:
            if var_name in line:
                color = line.split(":")[1].strip().rstrip(";")
                return color
    return None


def bind_theme(widget):
    theme_service = ThemeService()

    # are you from fabric or gtk?
    if hasattr(widget, "add_style_class") and hasattr(widget, "remove_style_class"):
        add_fn = widget.add_style_class
        remove_fn = widget.remove_style_class
    else:
        context = widget.get_style_context()
        add_fn = context.add_class
        remove_fn = context.remove_class

    def apply_theme(mode):
        if mode == ThemeMode.LIGHT:
            add_fn("light")
        else:
            remove_fn("light")

    apply_theme(theme_service.theme)
    theme_service.connect("theme-changed", lambda _, mode: apply_theme(mode))
