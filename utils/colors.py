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
