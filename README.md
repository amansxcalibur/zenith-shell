<h3 align="center">
  <img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/logos/all-logo.png" alt="Zenith Logo" width="60%"/>
</h3>

<div align="center">
  <p>A SOSS shell for <b>i3wm</b>, <b>sway</b> (including <b>swayFX</b>) and <b>Hyprland</b>, crafted using <a href="https://github.com/Fabric-Development/fabric">fabric</a>.</p>
</div>
<div align="center">
     <a href="https://ko-fi.com/amansxcalibur">
          <img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/badges/kofi.svg">
     </a>
    <a href="https://discord.gg/j6uwk2f2Zv">
          <img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/badges/discord.svg">
     </a>
     <br>
     <sub>Donations through Ko-Fi are welcome!
</div>

---

I've had a **LOT** of fun working with fabric and building this. I hope you do too :)

## Showcase

<table align="center">
  <tr>
    <td colspan="3"><img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/v3/dashboard.png" alt="Zenith dashboard" /></td>
  </tr>
  <tr>
    <td><img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/v3/player.png" alt="Zenith media player" /></td>
    <td><img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/v3/wallpaper.png" alt="Zenith wallpaper picker" /></td>
  </tr>
</table>

### Lockscreen

<img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/v3/lockscreen.png" alt="Zenith lockscreen" />

## Installation

### Requirements

Zenith supports **Arch-based** and **Ubuntu/Debian-based** distributions with **i3wm**, **sway** or **Hyprland**. **Python 3.10+** is required.

> [!IMPORTANT]
> **i3 users:** Rounded corners, true transparency, and other compositor effects require **picom v12 or newer**. Without it, curves are drawn without anti-aliasing.

> [!NOTE]
> **Hyprland users:** Version 0.55 or newer with a `hyprland.lua` config is required. Zenith won't touch a `hyprland.conf`.

### Install Zenith

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/amansxcalibur/zenith-shell/main/installer/install.sh)
```

<details>
<summary>Want to inspect the installer before running it?</summary>

Download the script and read it first:

```bash
curl -fsSLO https://raw.githubusercontent.com/amansxcalibur/zenith-shell/main/installer/install.sh
less install.sh
bash install.sh
```

Or clone the repository and run the installer from there:

```bash
git clone https://github.com/amansxcalibur/zenith-shell ~/.local/share/zenith-shell
~/.local/share/zenith-shell/installer/install.sh
```

</details>

### Installer options

| Option | Meaning |
| --- | --- |
| `--wm i3\|sway\|hyprland\|all` | Set up a specific window manager. By default, the installer detects it. |
| `--dry-run` | Run the checks and show the plan without making changes. |
| `-y`, `--yes` | Skip prompts and accept installing missing prerequisites, such as Rust or Go. |
| `-v`, `--verbose` | Show command output as it runs. |

### Launch Zenith

```bash
zenith-shell
```

Or just restart your session. If `zenith-shell` isn't found, add `~/.local/bin` to your `PATH` (`~/.zshrc` on zsh):

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

> [!TIP]
> **For best visual results on i3wm**: Start with the sample [`picom` configurations and GLSL shaders](https://github.com/amansxcalibur/zenith-shell/tree/main/config/picom).

## Usage

### Commands

| Command | What it does |
| --- | --- |
| `zenith-shell` | Start the shell. |
| `zenith-shell stop` / `restart` / `status` | Stop, restart, or check the running shell. |
| `zenith-shell settings` | Open the settings window. |
| `zenith-shell lock` | Lock the screen. Works with `xss-lock` and `swayidle -w`. |
| `zenith-shell --version` | Show the installed version. |
| `zenith-shell setup update` | Update Zenith and install any new dependencies. |
| `zenith-shell setup sync` | Install missing dependencies and set up a window manager. |
| `zenith-shell setup doctor` | Check that everything is installed and set up. |
| `zenith-shell setup logs` | Show the end of the installer log. |
| `zenith-shell setup uninstall [--purge]` | Remove Zenith. See [Uninstalling](#uninstalling). |

Run `zenith-shell setup` for a menu. On zsh, add `fpath=(~/.local/share/zsh/site-functions $fpath)` to `~/.zshrc` before `compinit` for tab completion.

### Configuration

Use `zenith-shell settings`, or edit `~/.config/zenith-shell/config.json` and restart the shell.

### Custom themes

Create a folder in `~/.config/zenith-shell/themes/` and add your colors as `light.css` and `dark.css`:

```
~/.config/zenith-shell/themes/
└── my-theme/
    ├── light.css
    └── dark.css
```

Start from the [example theme](examples/theme). Once it's done, restart the shell and it'll be in the wallpaper selector under `custom`.

### Updating

```bash
zenith-shell setup update
```

If you've edited a file the update touches, it stops and tells you which.

### Switching between window managers

```bash
zenith-shell setup sync --wm sway   # or i3, hyprland, all; detected if omitted
```

Installs what that window manager is missing and adds Zenith's keybindings and autostart to its config.

### Uninstalling

```bash
zenith-shell setup uninstall           # keep tools built from source
zenith-shell setup uninstall --purge   # also remove fabric-cli, gray, gtk-session-lock, matugen
```

Built tools are kept by default since other Fabric shells may use them. Decide on `--purge` up front, it can't be done later. You're asked whether to keep your config. System packages and your window manager config are never touched; what's left is printed for you to remove.

## Troubleshooting

- **Missing dependencies:** Run `zenith-shell setup doctor` to see what's missing.
- **Installer issues:** Check the full log at `~/.cache/zenith-shell/install.log`.
- **Conflicting keybindings:** Zenith never edits your existing bindings. If one of its keys is taken, the installer and the Keybindings tab in settings point it out. Rebind it with `zenith-shell settings` or remove it from your config, then reload your window manager.

## Dependencies and technical reference

The installer handles all of this. It's listed here if you'd rather set things up yourself.

### fabric ecosystem

- [fabric](https://github.com/Fabric-Development/fabric) - shell framework (via `requirements.txt`)
- [fabric-cli](https://github.com/Fabric-Development/fabric-cli) - CLI companion
- [gray](https://github.com/Fabric-Development/gray) - system tray support

### Utilities

- `playerctl` - MPRIS control
- `brightnessctl` - screen brightness control
- `libnotify` - notifications

### i3wm / X11

- `feh` - wallpaper setter
- `picom` - compositor (v12+)

### sway, Hyprland / Wayland

- `swaybg` - wallpaper setter
- `wl-clipboard` - clipboard access
- [gtk-layer-shell](https://github.com/wmww/gtk-layer-shell) - layer surfaces for the bar and dock
- [gtk-session-lock](https://github.com/Cu3PO42/gtk-session-lock) - lockscreen (built from source on Ubuntu)

### Themes and typography

- [matugen](https://github.com/InioX/matugen)
- [Roboto Flex](https://github.com/googlefonts/roboto-flex)
- [Google Sans Flex](https://fonts.google.com/specimen/Google+Sans+Flex)
- [Material Symbols](https://github.com/google/material-design-icons)

### Python

See `requirements.txt`.

### Libraries and build tools

- **Arch Linux:** `base-devel`, `git`, `curl`, `python`, `python-gobject`, `python-cairo`, `gtk3`, `libdbusmenu-gtk3`, `gobject-introspection`, `gnome-bluetooth-3.0`, `brightnessctl`, `playerctl`, `libnotify`, `libnm`, `librsvg`, `libpulse`, `bash-completion`, `meson`, `ninja`, `vala`
  - i3: `feh`, `picom`
  - sway, Hyprland: `swaybg`, `wl-clipboard`, `gtk-layer-shell`, `gtk-session-lock`
- **Ubuntu / Debian:** `build-essential`, `pkg-config`, `git`, `curl`, `meson`, `ninja-build`, `valac`, `python3-dev`, `python3-venv`, `python3-pip`, `libcairo2-dev`, `libgirepository1.0-dev`, `libgtk-3-dev`, `libdbusmenu-gtk3-dev`, `gir1.2-playerctl-2.0`, `gir1.2-gnomebluetooth-3.0`, `gir1.2-nm-1.0`, `gir1.2-rsvg-2.0`, `pulseaudio-utils`, `bash-completion`, `brightnessctl`, `libnotify-bin`
  - i3: `feh`, `picom`
  - sway, Hyprland: `swaybg`, `wl-clipboard`, `gir1.2-gtklayershell-0.1`, `libgtk-layer-shell0`, plus `libwayland-dev`, `gobject-introspection` and `gtk-doc-tools` to build `gtk-session-lock`

How the remaining tools are obtained depends on the distribution:

- **Arch Linux:** `matugen-bin` and `fabric-cli-git` come from the AUR (via `paru`, `yay`, or a `yay` installation built by the installer if neither is present). Other Arch dependencies come from the official repositories; only `gray` is built from source.
- **Ubuntu / Debian:** The following tools are built from source. Rust and Go are needed only if the corresponding tool is missing; the installer offers to install them if needed:
  - `matugen` with `cargo` (requires Rust)
  - `fabric-cli` with `meson` (requires Go)
  - `gray` with `meson`
  - `gtk-session-lock` with `meson` (sway and Hyprland only)

---

<table align="center">
  <tr>
    <td align="center">
      <b> sᴜᴘᴘᴏʀᴛ ᴛʜᴇ ᴘʀᴏᴊᴇᴄᴛ ~ ᴅʀᴏᴘ ᴀ ⭐️ ᴏʀ ᴀ <a href="https://ko-fi.com/amansxcalibur">☕</a></b>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img style="border:0px;height:300px;" src="https://user-images.githubusercontent.com/74038190/212259366-1e33063f-1384-459b-9ea5-8ee5e25b63dc.jpg" border="0" alt="Heya!" />
    </td>
  </tr>
</table>
