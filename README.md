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

> [!NOTE]
> Zenith has reached its first release! Happy ricing! :)

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

The installer runs its pre-flight checks first, including network access, build tools, and package availability. It then installs dependencies, creates a Python virtual environment, downloads fonts, and creates the `~/.local/bin/zenith-shell` launcher with tab completion for bash, zsh, and fish.

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

Append these options to the installer command when needed:

| Option | Meaning |
| --- | --- |
| `--wm i3\|sway\|all` | Set up a specific window manager. By default, the installer detects it. |
| `--dry-run` | Run the checks and show the plan without making changes. |
| `-y`, `--yes` | Skip prompts and accept installing missing prerequisites, such as Rust or Go. |
| `-v`, `--verbose` | Show command output as it runs. |

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
> **For best visual results on i3wm**: Start with the sample [`picom` configurations and GLSL shaders](https://github.com/amansxcalibur/zenith-shell/tree/main/config/picom).

## Usage

### Commands

| Command | What it does |
| --- | --- |
| `zenith-shell` | Start the shell. |
| `zenith-shell stop` / `restart` / `status` | Stop, restart, or check the running shell. |
| `zenith-shell settings` | Open the settings window. |
| `zenith-shell lock` | Lock the screen ([WIP](#lockscreen-wip)). Stays in the foreground, so it works with `xss-lock` and `swayidle -w`. |
| `zenith-shell --version` | Show the installed version. |
| `zenith-shell setup update` | Update Zenith and install any new dependencies. |
| `zenith-shell setup sync` | Install missing dependencies and set up a window manager. |
| `zenith-shell setup doctor` | Check dependencies, the virtual environment, launcher, fonts, and autostart. |
| `zenith-shell setup logs` | Show the end of the installer log. |
| `zenith-shell setup uninstall [--purge]` | Remove Zenith. See [Uninstalling](#uninstalling). |

Run `zenith-shell setup` for a menu, or add `--help` to any `setup` command. `setup` commands can run while the shell is running; restart it afterwards.

Tab completion works in bash, zsh, and fish once you open a new terminal. On zsh, add `fpath=(~/.local/share/zsh/site-functions $fpath)` to `~/.zshrc` before `compinit`.

### Configuration

All settings live in one file:

```
~/.config/zenith-shell/config.json
```

Change them with `zenith-shell settings`, which shows this path at the bottom with a button to copy it, or edit the file by hand and restart the shell.

### Updating

```bash
zenith-shell setup update
```

Pulls the latest changes and installs any new dependencies. If you've edited a file the update would change, it stops and names the file; other edits are left alone.

### Switching between i3 and sway

```bash
zenith-shell setup sync --wm sway   # or i3, all; detected if omitted
```

Installs only what that window manager is missing, then adds Zenith's keybindings and autostart to its config. If it has no config yet, one is created from the system default, without its bar and with clashing keybindings commented out.

### Uninstalling

```bash
zenith-shell setup uninstall           # keep tools built from source
zenith-shell setup uninstall --purge   # also remove fabric-cli, gray, gtk-session-lock, matugen
```

Built tools are kept by default because other Fabric-based shells may use them. Decide on `--purge` up front: their build files are deleted with Zenith, so they can't be removed later.

- **Config:** you're asked whether to keep your settings. If you keep them, `~/.config/zenith-shell/` is left in place and used again on the next install.
- **System packages** are never removed. The exact removal command is printed for you to review and run.
- **Leftovers:** i3/sway config lines and symlinks that point at Zenith are listed for you to remove.
- **Local changes:** if the install directory has edits or unpushed commits, you're warned, and `--yes` refuses to continue.

## Troubleshooting

- **Missing dependencies:** Run `zenith-shell setup doctor` to see what's missing.
- **Installer issues:** Check the full log at `~/.cache/zenith-shell/install.log`.
- **Conflicting keybindings:** Zenith never edits bindings in your existing i3/sway config. If one of its keys is already in use, including in an included file, `install`, `sync`, `update` and `doctor` list the conflict and exit with an error, and the Keybindings tab of the settings window highlights it. To fix it, rebind the key with `zenith-shell settings`, which works even when the launcher's key is taken, or remove it from your config. Then reload your window manager to clear its error bar. Zenith's keybindings use `$mod`; if your config doesn't set it, Zenith sets it to the Super key (`Mod4`).
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

- **Arch Linux:** `base-devel`, `git`, `curl`, `python`, `python-gobject`, `python-cairo`, `gtk3`, `libdbusmenu-gtk3`, `gobject-introspection`, `gnome-bluetooth-3.0`, `brightnessctl`, `playerctl`, `libnotify`, `libnm`, `librsvg`, `libpulse`, `bash-completion`, `meson`, `ninja`, `vala`
- **Ubuntu / Debian:** `build-essential`, `pkg-config`, `git`, `curl`, `meson`, `ninja-build`, `valac`, `python3-dev`, `python3-venv`, `python3-pip`, `libcairo2-dev`, `libgirepository1.0-dev`, `libgtk-3-dev`, `libdbusmenu-gtk3-dev`, `gir1.2-playerctl-2.0`, `gir1.2-gnomebluetooth-3.0`, `gir1.2-nm-1.0`, `gir1.2-rsvg-2.0`, `pulseaudio-utils`, `bash-completion`, `brightnessctl`, `libnotify-bin`

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
