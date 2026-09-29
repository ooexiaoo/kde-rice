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
white text on a pale green panel. Two things are generated with that in mind:

**The panel.** `kde-material-you-colors` writes no `[Colors:Highlight]` group at
all, so Panel Colorizer falls back to the base theme's highlight and keeps its
own text color. The script writes the group itself, taking the panel background
from the wallpaper primary and picking the text by WCAG contrast — on the
wallpaper in the screenshot that is `#1a1b00` on `#eaffb9`, 16.2:1.

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

The script can also be run by hand at any time:

```sh
python3 ~/.config/starship-matyou.py
```

## Troubleshooting

**Colors aren't changing.** Check the widget is present on the panel and that
*Script* in its settings points at `~/.config/starship-matyou.py`. Run the script
manually — it prints the colors it extracted and each target it updated.

**Panel text is hard to read.** `starship-matyou.py` writes `[Colors:Highlight]`
into the generated scheme, but the backend rewrites that file on every wallpaper
change. If you ever run the backend directly, run the script afterwards. To
confirm the group survived: `grep -A3 Colors:Highlight ~/.local/share/color-schemes/MaterialYouDark.colors`.

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

[krohnkite]: https://codeberg.org/anametologin/Krohnkite
[activeaccent]: https://github.com/nclarius/Plasma-window-decorations
[panelcolorizer]: https://github.com/luisbocanegra/plasma-panel-colorizer
[spacer]: https://github.com/luisbocanegra/plasma-panel-spacer-extended
[matyou]: https://github.com/luisbocanegra/kde-material-you-colors
[matyoustore]: https://store.kde.org/p/2136963
[mikedesk]: https://github.com/codelovesme/mike-desktop
