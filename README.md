<h1 align="center">
  <img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/sparkles.gif" alt="Sparkles" width="25" height="25" />
  <b>ZENITH</b>
  <img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/sparkles.gif" alt="Sparkles" width="25" height="25" />
</h1>

A SOSS shell for **i3wm**/**sway** (including **swayFX**), crafted using [fabric](https://github.com/Fabric-Development/fabric). The shell features a plethora of widgets with an easily configurable and modular system. I've had a **LOT** of fun working with fabric and building this. I hope you do too!

> [!WARNING]
> This project is nearing its first **stable release**. Installers are available, but **some breaking changes** may still occur **:)**

<h2>Showcase</h2>

<table align="center">
<tr>
<td colspan="3"><img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/dashboard-m3.png"></td>
</tr>
<tr>
<td colspan="1"><img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/launcher-1.png"></td>
<td colspan="1"><img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/player-1.png"></td>
<td colspan="1"><img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/wallpaper-1.png"></td>
</tr>
</table>

### LockScreen (WIP)

<img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/lockscreen-1.png">

> [!WARNING]
> The lockscreen is currently a WIP and may not handle all edge cases. While barely functional, it is far from secure. Please test thoroughly in a safe environment before relying on it for security-critical scenarios.

## Installation

Works on **Arch-based** and **Ubuntu/Debian-based** distros, with **i3wm**, **sway**, or both. Python 3.10+ is required.

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/amansxcalibur/zenith-shell/main/installer/install.sh)
```

> [!NOTE]
> The installer runs all its pre-flight checks first (network access, build tools, whether every package exists on your system). Then it installs the dependencies, sets up a Python virtual environment, downloads fonts, and creates a launcher at `~/.local/bin/zenith-shell`.

<details>
<summary>Want to read the script before running it?</summary>

```bash
curl -fsSLO https://raw.githubusercontent.com/amansxcalibur/zenith-shell/main/installer/install.sh
less install.sh
bash install.sh
```

Or clone the repo yourself:

```bash
git clone https://github.com/amansxcalibur/zenith-shell ~/.config/zenith-shell
~/.config/zenith-shell/installer/install.sh
```

</details>

Useful installer options (append them to any of the commands above):

| Option | Meaning |
| --- | --- |
| `--wm i3\|sway\|both` | Set up for a specific window manager. Default: detect it |
| `--dry-run` | Run the checks and show the plan, change nothing |
| `-y`, `--yes` | Don't ask questions (accepts installing missing prerequisites such as Rust/Go) |

After installation, run:

```bash
zenith-shell
```

Or restart your i3wm/sway session.

> [!TIP]
> If `zenith-shell` is not found after install, add `~/.local/bin` to your PATH (use `~/.zshrc` instead of `~/.bashrc` if you use zsh):
>
> ```bash
> echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
> ```

## Usage

| Command | What it does |
| --- | --- |
| `zenith-shell` | Start the shell |
| `zenith-shell restart` | Stop the running shell and start it again |
| `zenith-shell setup update` | Pull the latest changes, then install any new dependencies |
| `zenith-shell setup sync` | Install only what's missing for your window manager |
| `zenith-shell setup doctor` | Show which dependencies are present or missing |
| `zenith-shell setup uninstall` | Remove Zenith Shell |

`zenith-shell setup --help` lists all options. The `setup` commands can be run while the shell is running; restart the shell afterwards to pick up changes.

### Updating

```bash
zenith-shell setup update
```

This fetches the latest commits, shows what's coming, fast-forwards the repository, and then runs the *new* version of the installer to pick up any new dependencies. If you've edited a file that the update also changes, it stops before touching anything and tells you which file. Edits to other files are left alone.

### Switching between i3 and sway

Dependencies are tracked per window manager. If you start with i3 and move to sway later (or the other way around), run:

```bash
zenith-shell setup sync --wm sway
```

Only the missing pieces are installed. When the shell starts under a window manager that hasn't been set up yet, it sends a notification pointing you to this command.

### Uninstalling

```bash
zenith-shell setup uninstall
```

You'll be asked whether to keep your `config/config.json`; if you do, it is saved to `~/.config/zenith-shell-backup/` and restored on the next fresh install. Add `--purge` to also remove tools the installer built from source (`fabric-cli`, `gray`, `gtk-session-lock`, `matugen`). System packages are never removed automatically; the command prints the exact command for the ones the installer added, so you can review it first. i3/sway config lines that mention Zenith are listed for you to remove by hand.

### Troubleshooting

- Run `zenith-shell setup doctor` to see what's missing.
- The full installer log is at `~/.cache/zenith-shell/install.log`.
- The installer adds keybindings to your i3/sway config. If you already use the same keys, your WM may warn about duplicates. Review `~/.config/<i3|sway>/config`.
- On i3, picom **v12 or newer** is needed for rounded corners and true transparency and other effects. Older or distro-patched builds may warn or miss effects. Upstream: [yshui/picom](https://github.com/yshui/picom).

> [!Warning]
> **DO NOT TURN ON SCREEN CORNERS WITHOUT PICOM**. Your whole screen will appear black because the screen corner window is not transparent and spans throughout the screen.

## Dependencies

The installer handles these automatically. Listed here for reference.

**Fabric ecosystem**

- [fabric](https://github.com/Fabric-Development/fabric) - shell framework (via `requirements.txt`)
- [fabric-cli](https://github.com/Fabric-Development/fabric-cli) - CLI companion
- [gray](https://github.com/Fabric-Development/gray) - system tray support

**Utilities**

- `playerctl` - MPRIS control
- `brightnessctl` - screen brightness control
- `libnotify` - notifications

**i3wm / X11**

- `feh` - wallpaper setter
- `picom` - compositor (v12+)

**sway / Wayland**

- `swaybg` - wallpaper setter
- `wl-clipboard` - clipboard access
- [gtk-layer-shell](https://github.com/wmww/gtk-layer-shell) - layer surfaces for the bar and dock
- [gtk-session-lock](https://github.com/Cu3PO42/gtk-session-lock) - lockscreen (built from source on Ubuntu)

**Themes and Typography**

- [matugen](https://github.com/InioX/matugen) - dynamic Material You theming
- [Roboto Flex](https://github.com/googlefonts/roboto-flex)
- [Google Sans Flex](https://fonts.google.com/specimen/Google+Sans+Flex)
- [Material Symbols](https://github.com/google/material-design-icons)

**Python** - 3.10+, see `requirements.txt`

**Libraries and build tools** (always installed)
 
- **Arch Linux:** `base-devel`, `git`, `curl`, `python`, `python-gobject`, `python-cairo`, `gtk3`, `libdbusmenu-gtk3`, `gobject-introspection`, `gnome-bluetooth-3.0`
- **Ubuntu / Debian:** `build-essential`, `pkg-config`, `git`, `curl`, `meson`, `ninja-build`, `valac`, `python3-dev`, `python3-venv`, `python3-pip`, `libcairo2-dev`, `libgirepository1.0-dev`, `libgtk-3-dev`, `libdbusmenu-gtk3-dev`


Not available as packages, so they're built from source:
- `matugen` with `cargo` (needs Rust)
- `fabric-cli` with `meson` (needs Go)
- `gray` with `meson`
- `gtk-session-lock` with `meson` (sway only)

Rust and Go are only needed when the matching tool is missing, and the installer offers to install them for you. On i3, check that apt's `picom` is v12 or newer (see Troubleshooting).

---

<table align="center">
<tr>
<td align="center">
<img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/sparkles.gif" alt="Sparkles" width="16" height="16" />
<b> sᴜᴘᴘᴏʀᴛ ᴛʜᴇ ᴘʀᴏᴊᴇᴄᴛ ~ ᴅʀᴏᴘ ᴀ ⭐️ </b>
<img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/sparkles.gif" alt="Sparkles" width="16" height="16" />
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