<h1 align="center">
  <img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Telegram-Animated-Emojis/main/Activity/Sparkles.webp" alt="Sparkles" width="25" height="25" />
  <b>ZENITH</b>
  <img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Telegram-Animated-Emojis/main/Activity/Sparkles.webp" alt="Sparkles" width="25" height="25" />
</h1>

A SOSS shell for **X11** and **i3wm**, crafted using [fabric](https://github.com/Fabric-Development/fabric). The shell features a plethora of widgets with an easily configurable and modular system. I've had a **LOT** of fun working with fabric and building this — I hope you do too!

> [!WARNING]
> This project is nearing its first **stable release**. Installers are available, but **some breaking changes** may still occur **:)**

<h2>Showcase</h2>

<table align="center">
<tr>
<td colspan="3"><img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/dashboard.png"></td>
</tr>
<tr>
<td colspan="1"><img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/launcher.png"></td>
<td colspan="1"><img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/player.png"></td>
<td colspan="1"><img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/wallpaper-selector.png"></td>
</tr>
</table>

### LockScreen (WIP)

<img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/lockscreen.png">

> [!WARNING]
> The lockscreen is currently a WIP and may not handle all edge cases. While barely functional, it is far from secure. Please test thoroughly in a safe environment before relying on it for security-critical scenarios.

## Installation

> [!NOTE]
> The installer will set up all dependencies, configure a Python virtual environment, download fonts, and create a launcher at `~/.local/bin/zenith-shell`.

**Arch Linux**

```bash
curl -sSL https://raw.githubusercontent.com/amansxcalibur/zenith-shell/main/install_arch.sh | bash
```

**Ubuntu / Debian**

```bash
curl -sSL https://raw.githubusercontent.com/amansxcalibur/zenith-shell/main/install_ubuntu.sh | bash
```

After installation, run:

```bash
zenith-shell
```

Or restart your i3wm session.

> [!TIP]
> If `zenith-shell` is not found after install, add `~/.local/bin` to your PATH:
>
> ```bash
> echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
> ```

## Dependencies

The installers handle these automatically. Listed here for reference.

**Fabric ecosystem**

- [fabric](https://github.com/Fabric-Development/fabric) - shell framework (via `requirements.txt`)
- [fabric-cli](https://github.com/Fabric-Development/fabric-cli) - CLI companion
- [gray](https://github.com/Fabric-Development/gray) - system tray support

**Other utilities**

- `feh` - wallpaper setter
- `playerctl` - MPRIS control
- `brightnessctl` - screen brightness control

**Themes and Typography**

- [matugen](https://github.com/InioX/matugen) - dynamic Material You theming
- [Roboto Flex](https://github.com/googlefonts/roboto-flex)
- [Material Symbols](https://github.com/google/material-design-icons)

**Python** - see `requirements.txt`

**Arch-only (AUR)**

- `python-gobject`, `python-cairo`, `gobject-introspection`, `gnome-bluetooth-3.0`, `libdbusmenu-gtk3`, `libnotify`

**Ubuntu-only (apt)**

- `python3-dev`, `python3-venv`, `python3-pip`, `libcairo2-dev`, `libgirepository1.0-dev`, `libgtk-3-dev`, `libdbusmenu-gtk3-dev`, `gir1.2-playerctl-2.0`, `build-essential`, `pkg-config`, `meson`, `ninja-build`, `valac`

---

<table align="center">
<tr>
<td align="center">
<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Telegram-Animated-Emojis/main/Activity/Sparkles.webp" alt="Sparkles" width="16" height="16" />
<b> sᴜᴘᴘᴏʀᴛ ᴛʜᴇ ᴘʀᴏᴊᴇᴄᴛ ~ ᴅʀᴏᴘ ᴀ ⭐️ </b>
<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Telegram-Animated-Emojis/main/Activity/Sparkles.webp" alt="Sparkles" width="16" height="16" />
</td>
</tr>
<tr>
<td align="center">
<img style='border:0px;height:300px;'
src='https://user-images.githubusercontent.com/74038190/212259366-1e33063f-1384-459b-9ea5-8ee5e25b63dc.jpg'
border='0' alt='Heya!' />
</td>
</tr>
</table>
