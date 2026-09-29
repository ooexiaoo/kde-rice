# kde-rice

A Fedora KDE Plasma 6 desktop where the wallpaper is the only thing you actually
change. Everything else — panel, window borders, terminal, prompt, `fastfetch`,
even the browser toolbar and Obsidian accent — re-derives its colors from it.

<!-- Screenshots: drop them in assets/ and reference them here. -->

## The idea

Plasma 6's window manager is KWin, not a standalone tiling WM. The tiling comes
from [Kröhnkite][krohnkite], a dynamic tiling *script* that runs inside KWin, so
you keep Plasma's panel, activities, and applets while getting dwm-style window
management. Set `Meta+T` for tile, `Meta+M` for monocle, `Meta+\` to cycle layouts.

The color pipeline is one hook:

```
wallpaper change
      │
      ▼
KDE Material You Colors   extracts the dominant color, writes a Material You
(Plasma widget)           scheme into ~/.local/share/color-schemes/
      │
      ├── on_change_hook ──▶ starship-matyou.py
      │                          ├── starship.toml     palette 'material_you'
      │                          ├── fastfetch         key + title colors
      │                          ├── Obsidian          accentColor
      │                          └── Brave              BrowserThemeColor
      │
      ▼
KDE theme, panel colorizer, Aurorae window borders
```

`starship-matyou.py` reads the generated `.colors` file, maps the Material You
roles onto Starship palette slots, and rewrites the four targets above. The
Obsidian and Brave targets are opt-in — see [Configuration](#configuration).

The shipped scheme variant is `Vibrant` with `chroma_multiplier=10`, which is
what keeps the accent colors saturated without a patched backend.

## Contrast

Wallpaper-derived color is the whole point, and it is also how you end up with
text that is unreadable. Two things are generated with that in mind:

**The panel.** `kde-material-you-colors` writes no `[Colors:Highlight]` group at
all, so Panel Colorizer falls back to the base theme's highlight and keeps its
own text color. The script writes the group itself, deriving both the panel
background and its text from the wallpaper as described in
[Panel text color](#panel-text-color) — on the wallpaper in the screenshot that
is `#fff5ec` on `#6d4019`, 8.1:1. The same text is also written into
`plasma-org.kde.plasma.desktop-appletsrc`, because the palette value alone
cannot stay legible on every surface the text lands on.

**The prompt.** `starship.toml` fixes which palette slot is text on which
background, but the colors behind those slots change with every wallpaper. Three
segments (`git_branch`, `git_status`, `directory`) sit on the wallpaper primary
itself, so their text can't be a fixed slot — it is resolved per wallpaper into
`color_on_accent` and `color_on_accent_dim`. The remaining accents are nudged
until they clear 4.5:1 against the specific backgrounds they are drawn on.

Check it at any time:

```sh
python3 ~/.config/starship-matyou.py --check
```

```
  ok   directory.style        color_on_accent on color_purple   16.2:1
  ok   git_status.style       color_on_accent_dim on color_purple    5.3:1
  seam format                 color_green on color_blue2    1.6:1
  ...
  11/11 text pairs pass WCAG AA (4.5:1); seams listed above are decorative
```

`seam` rows are the powerline arrow glyphs, which are drawn as one segment's
background on the next one's. Two neighbouring light segments give a faint
seam; that is a cosmetic limit of the chain, not unreadable text, so it is
reported without failing the audit.

## What's in here

| Path | What it does |
|------|--------------|
| `.config/kde-material-you-colors/config.conf` | Backend config: scheme variant, the `on_change_hook`, Konsole theming |
| `.config/starship-matyou.py` | The sync script described above, plus `--check` for the contrast audit |
| `.config/plasma-org.kde.plasma.desktop-appletsrc` | Panel layout, desktop containment, Panel Colorizer settings |
| `.config/kwinrc` | Kröhnkite enabled, Breeze → Aurorae window decorations |
| `.config/kdeglobals` | Global theme, `MaterialYouDark` color scheme, Breeze theme tuning |
| `.config/starship.toml` | Prompt, with an auto-generated `material_you` palette block |
| `.config/fastfetch/config.jsonc` | `fastfetch` layout; colors are rewritten by the script |
| `.config/fastfetch/logo.png` | Logo `fastfetch` renders. Not ours — see [Credits](#credits) |
| `.config/kwinrulesrc` | Per-app window rules |
| `.config/konsole/`, `.config/konsolerc` | Konsole profile using the generated `MaterialYouAlt` scheme |
| `.config/plasmashellrc` | Plasma shell settings |

Third-party pieces are **not** vendored here. `install.sh` pulls them from
upstream, so you always get current versions:

| Component | Source |
|-----------|--------|
| Kröhnkite (KWin tiling) | [codeberg.org/anametologin/Krohnkite][krohnkite] |
| ActiveAccent window decoration | [github.com/nclarius/Plasma-window-decorations][activeaccent] |
| Panel Colorizer | [github.com/luisbocanegra/plasma-panel-colorizer][panelcolorizer] |
| Panel Spacer Extended | [github.com/luisbocanegra/plasma-panel-spacer-extended][spacer] |
| KDE Material You Colors widget | [KDE Store][matyoustore] |
| Mike Desktop (virtual desktops) | [store.kde.org][mikedesktop] |

## Requirements

- Fedora with KDE Plasma 6, Wayland session
- `starship`, `fastfetch`, `zsh`, a Nerd Font, and `kde-material-you-colors`

`install.sh --deps` installs all of them, but the pieces that matter to
understand are:

```sh
pipx install kde-material-you-colors
```

The widget itself is not on PyPI — add **KDE Material You Colors** to your panel
via *Get New Widgets* ([KDE Store][matyoustore]). It has to be the widget
running, not just the CLI, because the widget is what fires the hook on every
wallpaper change.

## Install

```sh
git clone https://github.com/ooexiaoo/kde-rice
cd kde-rice
./install.sh
```

`./install.sh --config` and `--extras` do the two halves separately. Existing
files are copied to `~/<path>.bak-<timestamp>` before anything is overwritten.

The shipped `plasma-org.kde.plasma.desktop-appletsrc` has an **empty wallpaper
path** on purpose, so installing does not change your current wallpaper. Set one
afterwards and the pipeline starts on its own.

## Configuration

Obsidian and Brave are off by default. To enable either, copy the example and
uncomment what you want:

```sh
cp ~/.config/starship-matyou.conf.example ~/.config/starship-matyou.conf
```

```ini
[sync]
obsidian_vault = ~/Notes/MyVault
brave_policy_dir = /etc/brave/policies/managed
widget_text = auto
```

- **`obsidian_vault`** — writes `accentColor` into
  `<vault>/.obsidian/appearance.json`.
- **`brave_policy_dir`** — writes a managed Chromium policy file containing
  `BrowserThemeColor`. Brave watches that file live and re-themes itself with no
  extension and no restart. The directory is system-level, so **this one needs
  root**:

  ```sh
  sudo install -d -m 755 /etc/brave/policies/managed
  sudo chown -R "$USER" /etc/brave/policies/managed
  ```

- **`widget_text`** — which way the panel widget text is walked away from the
  wallpaper primary. Defaults to `auto`; see
  [Panel text color](#panel-text-color).

The script can also be run by hand at any time:

```sh
python3 ~/.config/starship-matyou.py
```

## Panel text color

The top bar carries the clock, the task manager, and the **Application Menu**
popup with its *File / Edit / View* entries. Two things get written, and they are
deliberately different mechanisms:

| What | Where | How |
| --- | --- | --- |
| Panel background | `[Colors:Highlight]` in the scheme | `backgroundColor` |
| Widget / menu text | `plasma-org.kde.plasma.desktop-appletsrc` | `sourceType: 0` (custom) |

The text is **not** left as a palette lookup. Panel Colorizer normally draws it
from `highlightedTextColor`, but the panel, the task manager and the Application
Menu popup are separate surfaces with separate backgrounds, and one shared
palette entry cannot stay legible on all of them.

### Why the panel is dark

Panel Colorizer sets the panel background but **never recolors the panel's own
text** — `CustomBackground.qml` returns early for `isPanel` — so that text stays
whatever the Plasma widget style draws, which is a near-white. A light panel
therefore cannot be made legible at all, no matter what goes in the palette.

It also reverts items to the style color when window focus changes without
re-applying, which on a light panel shows up as the text flashing between two
very different colors when you switch windows. On a dark panel both the widget's
color and the style's fallback are light, so the flash is invisible.

So the panel background is the wallpaper primary darkened and muted until light
text clears **7:1** — AAA rather than AA, because the widget style's own text
sits on this same surface and is not under this script's control.

### How the tint is derived

The wallpaper hue has to survive without the color turning into mud or neon.
Two failure modes to avoid:

- **Darkening alone** keeps full saturation, so a pale red primary lands on a
  vivid red — a different color, not a dark tint of the wallpaper.
- **Muting per step** compounds, because a pale wallpaper needs many steps to
  reach the target while an already-dark one needs none. A pale green ends up
  flat grey, losing the tint entirely.

So the mute is applied **once**, scaled by how far the color actually had to be
darkened. A wallpaper that was already dark keeps its chroma; one that had to
travel a long way is muted proportionally:

| Wallpaper primary | Panel background | Text | Contrast |
| --- | --- | --- | --- |
| `#ff9b48` orange | `#6d4019` | `#fff5ec` | 8.1:1 |
| `#eaffb9` pale green | `#344116` | `#fcfff8` | 10.9:1 |
| `#9aa4ff` periwinkle | `#1c32dd` | `#f4f5ff` | 7.6:1 |
| `#ff8797` pale red | `#871e2c` | `#fff3f4` | 8.6:1 |
| `#0f0f00` near-black | `#0f0f00` | `#e7e7e5` | 15.6:1 |
| `#004d40` dark teal | `#004d40` | `#e5edeb` | 8.3:1 |

If you have overridden the panel background to something light and want dark
text to match, force it:

```ini
[sync]
widget_text = dark
```

Then re-run the script.

## Top bar widgets

The layout is a single floating panel on the bottom edge, left to right:

| # | Widget | Plugin ID | Source |
|---|--------|-----------|--------|
| 143 | Application Launcher | `org.kde.plasma.kickoff` | stock |
| 136 | Virtual desktops | `com.mike.desktop` | third-party |
| 59 | Global Menu (File / Edit / View) | `org.kde.plasma.appmenu` | stock |
| 135 | Panel Spacer | `luisbocanegra.panelspacer.extended` | third-party |
| 5 | Icons-only Task Manager | `org.kde.plasma.icontasks` | stock |
| 81 | Digital Clock | `org.kde.plasma.digitalclock` | stock |
| 104 | Panel colorizer | `luisbocanegra.panel.colorizer` | third-party |
| 82 | KDE Material You Colors | `luisbocanegra.kdematerialyou.colors` | third-party |
| 63 | System Tray | `org.kde.plasma.systemtray` | stock |

The three `luisbocanegra` widgets are the color pipeline: **KDE Material You
Colors** regenerates the scheme from the wallpaper, **Panel colorizer** repaints
the panel background from it, and the **spacer** is what pushes the clock and
tray to the right edge. Global Menu is deliberately a *panel* widget rather than
a launcher-menu plugin, because the panel text color written by
[Panel text color](#panel-text-color) reaches it through
`plasma-org.kde.plasma.desktop-appletsrc`.

### Setting it up

On a clean system, `install.sh` does this for you — it rsyncs the whole
`.config/` tree, which includes the layout file.

If you already have a Plasma setup you want to keep, **do not run `install.sh`
blind**; it will overwrite your panel. Copy just the layout instead:

```sh
systemctl --user stop plasma-plasmashell.service
cp .config/plasma-org.kde.plasma.desktop-appletsrc ~/.config/
systemctl --user start plasma-plasmashell.service
```

Plasma rewrites this file constantly, so edit it with `plasmashell` stopped or
your changes get clobbered. The layout is resolution-independent: it stores
widget *order* only, with no hardcoded positions or panel height, so applets
land the same way on any screen size. The spacer applet does write a `screenWidth`
cache into your copy at runtime — that is the widget measuring your screen, and it
is safe to leave alone.

To add a widget by hand instead, use *System Settings → Desktop Shell → Widgets*,
add each of the four third-party plugins from the table above, and keep the left
half in the order listed.

## Troubleshooting

**Colors aren't changing.** Check the widget is present on the panel and that
*Script* in its settings points at `~/.config/starship-matyou.py`. Run the script
manually — it prints the colors it extracted and each target it updated.

**Panel text is hard to read.** `starship-matyou.py` writes `[Colors:Highlight]`
into the generated scheme, but the backend rewrites that file on every wallpaper
change. If you ever run the backend directly, run the script afterwards. To
confirm the group survived: `grep -A3 Colors:Highlight ~/.local/share/color-schemes/MaterialYouDark.colors`.

**Top bar text is the wrong shade.** See [Panel text color](#panel-text-color).
If you have set a light panel background of your own, set `widget_text = dark`
and re-run the script.

**Kröhnkite isn't tiling.** Config changes need a reboot, not a script
toggle — toggling it off and on starts multiple instances. Log out and back in.

**Aurorae decoration doesn't show up.** On KWin 6 the theme directory needs a
`metadata.json`, not just `metadata.desktop`, or it won't be discovered.

**Konsole colors are wrong.** The profile points at `MaterialYouAlt`, which is
generated by the backend. If you deleted the generated scheme, re-run the script.

## Credits

- [KDE Material You Colors][matyou] by Luis BMC — MIT
- [Kröhnkite][krohnkite] by Eon S. Jeon — MIT
- [ActiveAccent][activeaccent] by Natalie Clarius — GPL-3.0
- [Panel Colorizer][panelcolorizer], [Panel Spacer Extended][spacer] by Luis BMC — MIT
- [Mike Desktop][mikedesk] by Miguel de la Cruz — GPL-3.0

`.config/fastfetch/logo.png` is a **Gundam** image. It is not ours and not
covered by any license grant in this repo — it is third-party artwork from
Bandai Namco / Sunrise's *Mobile Suit Gundam* franchise, redistributed here as a
personal configuration sample. Swap it for your own (that is what
`.gitignore` allows) if you intend to publish or redistribute this repo.

[krohnkite]: https://codeberg.org/anametologin/Krohnkite
[activeaccent]: https://github.com/nclarius/Plasma-window-decorations
[panelcolorizer]: https://github.com/luisbocanegra/plasma-panel-colorizer
[spacer]: https://github.com/luisbocanegra/plasma-panel-spacer-extended
[matyou]: https://github.com/luisbocanegra/kde-material-you-colors
[matyoustore]: https://store.kde.org/p/2136963
[mikedesktop]: https://store.kde.org/p/1127745
[mikedesk]: https://github.com/codelovesme/mike-desktop
