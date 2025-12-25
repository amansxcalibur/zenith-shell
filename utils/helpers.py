def toggle_class(widget, remove, add):
    widget.remove_style_class(remove)
    widget.add_style_class(add)


# todo
# def toggle_style_class(widget, style_class):
#     if widget.has_style_class(style_class):
#         widget.remove_style_class(style_class)
#     else:
#         widget.add_style_class(style_class)


def toggle_config_vertical_flag():
    import os
    CONFIG_PATH = os.path.expanduser("~/fabric/config/info.py")
    with open(CONFIG_PATH, "r") as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip().startswith("VERTICAL"):
            current_value = "True" in line
            new_value = "False" if current_value else "True"
            new_lines.append(f"VERTICAL = {new_value}\n")
        else:
            new_lines.append(line)

    with open(CONFIG_PATH, "w") as f:
        f.writelines(new_lines)


_settings_process = None

def open_settings():
    global _settings_process

    if _settings_process and not _settings_process.get_if_exited():
        return
    
    from fabric.utils.helpers import exec_shell_command_async
    import sys, os

    FONT_RESOLVER = os.path.expanduser("~/fabric/font_variation_resolver.py")

    print("hello evrone", FONT_RESOLVER)

    _settings_process, _ = exec_shell_command_async([
        sys.executable,
        str(FONT_RESOLVER),
    ])
