<h3 align="center">
  <img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/logos/all-logo.png" alt="Zenith Logo" width="60%"/>
</h3>

<div align="center">
  <p>A SOSS shell for <b>i3wm</b> and <b>sway</b> (including <b>swayFX</b>), crafted using <a href="https://github.com/Fabric-Development/fabric">fabric</a>.</p>
</div>
<div align="center">
     <a href="https://ko-fi.com/amansxcalibur">
          <img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/badges/kofi.svg">
     </a>
     <br>
     <sub>Donations through Ko-Fi are welcome!
</div>

---

I've had a **LOT** of fun working with fabric and building this. I hope you do too :)

> [!WARNING]
> Zenith is nearing its first **stable release**. Installers are available, but some breaking changes may still occur. :)

## Showcase

<table align="center">
  <tr>
    <td colspan="3"><img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/dashboard-m3-2.png" alt="Zenith dashboard" /></td>
  </tr>
  <tr>
    <td><img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/launcher-1.png" alt="Zenith launcher" /></td>
    <td><img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/player-1.png" alt="Zenith media player" /></td>
    <td><img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/wallpaper-2.png" alt="Zenith wallpaper picker" /></td>
  </tr>
</table>

### Lockscreen (WIP)

<img src="https://amansxcalibur.github.io/zenith-resources/reverse-bar/screenshots/lockscreen-1.png" alt="Zenith lockscreen" />

> [!WARNING]
> The lockscreen is a work in progress and may not handle all edge cases. It is far from secure. Test thoroughly in a safe environment before relying on it for security-critical scenarios.

## Installation

### Requirements

Zenith supports **Arch-based** and **Ubuntu/Debian-based** distributions with **i3wm**, **sway**, or both. **Python 3.10+** is required.

> [!IMPORTANT]
> **i3 users:** Rounded corners, true transparency, and other compositor effects require **picom v12 or newer**. **Do NOT enable screen corners** without a compatible picom compositor; the screen may appear black. See [Troubleshooting](#troubleshooting).

### Install Zenith

Run the installer:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/amansxcalibur/zenith-shell/main/installer/install.sh)
```

The installer runs its pre-flight checks first, including network access, build tools, and package availability. It then installs dependencies, creates a Python virtual environment, downloads fonts, and creates the `~/.local/bin/zenith-shell` launcher.

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
git clone https://github.com/amansxcalibur/zenith-shell ~/.config/zenith-shell
~/.config/zenith-shell/installer/install.sh
```

</details>

### Installer options

Append these options to the installer command when needed:

| Option | Meaning |
| --- | --- |
| `--wm i3\|sway\|all` | Set up a specific window manager. By default, the installer detects it. |
| `--dry-run` | Run the checks and show the plan without making changes. |
| `-y`, `--yes` | Skip prompts and accept installing missing prerequisites, such as Rust or Go. |
| `--purge` | For `uninstall` only: also remove tools built from source. |

### Launch Zenith

After installation, start the shell with:

```bash
zenith-shell
```

You can also restart your i3wm/sway session.

If `zenith-shell` is not found, add `~/.local/bin` to your `PATH`. Use `~/.zshrc` instead of `~/.bashrc` if you use zsh:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

If Zenith does not start as expected, run `zenith-shell setup doctor` to check for missing dependencies. See [Troubleshooting](#troubleshooting) for other common issues.

> [!TIP]
> **For best visual results**: Start with the sample `picom` configurations and GLSL shaders located in `~/.config/zenith-shell/config/picom/`.

## Usage and management

### Commands

| Command | What it does |
| --- | --- |
| `zenith-shell` | Start the shell. |
| `zenith-shell setup update` | Fetch the latest changes and install any new dependencies. |
| `zenith-shell setup sync` | Install missing dependencies for the configured window manager. |
| `zenith-shell setup doctor` | Show which dependencies are present or missing. |
| `zenith-shell setup uninstall` | Remove Zenith Shell. |

Run `zenith-shell setup --help` to see all setup options. The `setup` commands can be run while the shell is running; restart the shell afterwards to pick up changes.

### Updating

```bash
zenith-shell setup update
```

This fetches the latest commits, shows what's coming, fast-forwards the repository, and runs the **new** version of the installer to pick up any new dependencies. If you've edited a file that the update would also change, the updater stops before touching anything and tells you which file. Edits to other files are left alone.

### Switching between i3 and sway

Dependencies are tracked separately for each window manager. If you start with i3 and later move to sway (or the other way around), run the relevant command. For example:

```bash
zenith-shell setup sync --wm sway
```
> [!NOTE]
> `zenith-shell setup sync` alone should detect and install dependencies. You can specify the window manager via `--wm i3|sway` to be elaborate 

Only missing components are installed. If Zenith starts under a window manager that hasn't been set up yet, it sends a notification pointing you to this command.

### Uninstalling

```bash
zenith-shell setup uninstall
```

You'll be asked whether to keep `config/config.json`. If you keep it, the file is saved to `~/.config/zenith-shell-backup/` and restored on the next fresh install.

Add `--purge` to also remove tools the installer built from source: `fabric-cli`, `gray`, `gtk-session-lock`, and `matugen`. System packages are never removed automatically. Instead, the command prints the exact removal command for packages added by the installer, so you can review it first. Any i3/sway configuration lines that mention Zenith are listed for you to remove manually.

## Troubleshooting

- **Missing dependencies:** Run `zenith-shell setup doctor` to see what's missing.
- **Installer issues:** Check the full log at `~/.cache/zenith-shell/install.log`.
- **Duplicate keybindings:** The installer adds keybindings to your i3/sway config. If you already use the same keys, your window manager may warn about duplicates. Review `~/.config/<i3|sway>/config`.
- **i3 compositor effects:** Rounded corners, true transparency, and other effects require picom **v12 or newer**. Older or distro-patched builds may warn or lack effects. See the upstream [yshui/picom](https://github.com/yshui/picom) project.
- **Screen appears black after enabling screen corners:** Disable screen corners until a compatible picom compositor is running. Do not enable screen corners without picom.

## Dependencies and technical reference

The installer handles these dependencies automatically. This section is provided for reference.

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

### sway / Wayland

- `swaybg` - wallpaper setter
- `wl-clipboard` - clipboard access
- [gtk-layer-shell](https://github.com/wmww/gtk-layer-shell) - layer surfaces for the bar and dock
- [gtk-session-lock](https://github.com/Cu3PO42/gtk-session-lock) - lockscreen (built from source on Ubuntu)

### Themes and typography

- [matugen](https://github.com/InioX/matugen) - dynamic Material You theming
- [Roboto Flex](https://github.com/googlefonts/roboto-flex)
- [Google Sans Flex](https://fonts.google.com/specimen/Google+Sans+Flex)
- [Material Symbols](https://github.com/google/material-design-icons)

### Python

Python 3.10+ is required. See `requirements.txt`.

### Libraries and build tools

These packages are installed as part of the setup process.

- **Arch Linux:** `base-devel`, `git`, `curl`, `python`, `python-gobject`, `python-cairo`, `gtk3`, `libdbusmenu-gtk3`, `gobject-introspection`, `gnome-bluetooth-3.0`, `brightnessctl`, `playerctl`, `libnotify`, `meson`, `ninja`, `vala`
- **Ubuntu / Debian:** `build-essential`, `pkg-config`, `git`, `curl`, `meson`, `ninja-build`, `valac`, `python3-dev`, `python3-venv`, `python3-pip`, `libcairo2-dev`, `libgirepository1.0-dev`, `libgtk-3-dev`, `libdbusmenu-gtk3-dev`, `gir1.2-playerctl-2.0`, `brightnessctl`, `libnotify-bin`

How the remaining tools are obtained depends on the distribution:

- **Arch Linux:** `matugen-bin` and `fabric-cli-git` come from the AUR (via `paru`, `yay`, or a `yay` installation built by the installer if neither is present). Other Arch dependencies come from the official repositories; only `gray` is built from source.
- **Ubuntu / Debian:** The following tools are built from source. Rust and Go are needed only if the corresponding tool is missing; the installer offers to install them if needed:
  - `matugen` with `cargo` (requires Rust)
  - `fabric-cli` with `meson` (requires Go)
  - `gray` with `meson`
  - `gtk-session-lock` with `meson` (sway only)

On i3, check that the version of picom available through apt is v12 or newer (see [Troubleshooting](#troubleshooting)).

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
