#!/usr/bin/env python3
"""
starship-matyou — syncs Material You wallpaper colors to everything else.

Reads the active KDE Material You color scheme and rewrites:
  - <scheme>.colors                        ([Colors:Highlight] for the panel)
  - ~/.config/plasma-org.kde.plasma.desktop-appletsrc
                                           (Panel Colorizer widget text)
  - ~/.config/starship.toml              (palette 'material_you')
  - ~/.config/fastfetch/config.jsonc      (key + title text colors)
  - <obsidian vault>/.obsidian/appearance.json  (accentColor)
  - /etc/brave/policies/managed/accent.json      (BrowserThemeColor)

Designed to be called by kde-material-you-colors on_change_hook.

Obsidian and Brave are opt-in: set them in ~/.config/starship-matyou.conf

    [sync]
    obsidian_vault = ~/Notes/MyVault
    brave_policy_dir = /etc/brave/policies/managed
    widget_text = auto          # auto | dark | light
A target with no configured path is skipped. Every path can also be overridden
per-invocation with the equivalent environment variable.
"""

import configparser
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
STARSHIP_CFG = Path.home() / ".config" / "starship.toml"
FASTFETCH_CFG = Path.home() / ".config" / "fastfetch" / "config.jsonc"
COLOR_SCHEMES = Path.home() / ".local" / "share" / "color-schemes"
KDEGLOBALS = Path.home() / ".config" / "kdeglobals"
SELF_CONF = Path.home() / ".config" / "starship-matyou.conf"


def _expand(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


def load_settings() -> dict:
    """Resolve optional target paths from ~/.config/starship-matyou.conf.

    Precedence: environment variable > config file > built-in default.
    An empty value means "skip this target".
    """
    defaults = {
        "obsidian_vault": "",
        "brave_policy_dir": "/etc/brave/policies/managed",
        "panel_appletsrc": str(
            Path.home() / ".config" / "plasma-org.kde.plasma.desktop-appletsrc"
        ),
        "widget_text": "auto",
    }
    # Keys that are plain values rather than filesystem paths.
    plain = {"widget_text"}

    conf = configparser.RawConfigParser()
    if SELF_CONF.exists():
        conf.read(SELF_CONF)

    resolved = {}
    for key, fallback in defaults.items():
        value = os.environ.get(key.upper(), None)
        if value is None:
            value = conf.get("sync", key, fallback=fallback) if conf.has_section("sync") else fallback
        if key in plain:
            resolved[key] = value or fallback
        else:
            resolved[key] = _expand(value) if value else None

    return resolved


SETTINGS = load_settings()

# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def hex_to_hsl(hex_color: str) -> tuple[float, float, float]:
    r, g, b = [c / 255.0 for c in hex_to_rgb(hex_color)]
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, l
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = (g - b) / d + (6 if g < b else 0)
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60, s, l


def hsl_to_hex(h: float, s: float, l: float) -> str:
    h = h % 360
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return rgb_to_hex(
        int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)
    )


def shift_hue(hex_color: str, degrees: float) -> str:
    h, s, l = hex_to_hsl(hex_color)
    return hsl_to_hex((h + degrees) % 360, s, l)


def set_lightness(hex_color: str, target_l: float) -> str:
    h, s, _l = hex_to_hsl(hex_color)
    return hsl_to_hex(h, s, max(0.0, min(1.0, target_l)))


def blend(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    return rgb_to_hex(
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


def strip_alpha(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    if len(h) == 8:
        return "#" + h[2:]
    return hex_color


# ---------------------------------------------------------------------------
# WCAG contrast
# ---------------------------------------------------------------------------

# WCAG 2.1 AA for normal text.
MIN_CONTRAST = 4.5


def relative_luminance(hex_color: str) -> float:
    def channel(value: int) -> float:
        c = value / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in hex_to_rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = relative_luminance(fg), relative_luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def readable_text_on(bg: str, light: str = "#fdfcf7", dark: str = "#1a1b00") -> str:
    """Pick text for bg: the tinted near-white/near-black pair if it clears AA,
    otherwise escalate to pure white or black.

    The tinted pair looks better on screen, but a mid-tone background leaves so
    little headroom that the tint alone can miss the ratio, so fall back to the
    extremes rather than ship unreadable text.
    """
    best = max((light, dark), key=lambda c: contrast_ratio(c, bg))
    if contrast_ratio(best, bg) >= MIN_CONTRAST:
        return best
    return max(("#ffffff", "#000000"), key=lambda c: contrast_ratio(c, bg))


# ---------------------------------------------------------------------------
# Panel colors
# ---------------------------------------------------------------------------

HIGHLIGHT_SECTION = "Colors:Highlight"


def build_highlight_group(p: dict) -> dict:
    """Panel background and text for Panel Colorizer.

    The generated Material You scheme has no [Colors:Highlight] group, so the
    panel falls back to the base theme's highlight and keeps white text on it.
    On a pale wallpaper primary that is unreadable. Derive both ends from the
    wallpaper instead, and pair the background with the same text Panel Colorizer
    is given, so the group and the widget config never disagree.

    The panel background is `p["primary"]` (Colors:Selection/BackgroundNormal),
    which is what Panel Colorizer's "highlightColor" resolves to. Do not
    substitute panel_background() here: that darkens the primary on the
    assumption the panel is dark, but the panel actually renders p["primary"]
    as-is. Deriving the text from the darkened value picks a light tint, and
    that light tint is what Theme.highlightedTextColor returns -- which is how
    the Global Menu ends up drawing near-white text on a pale panel as soon as
    it takes focus.
    """
    bg = p["primary"]
    fg = panel_text_color(p, bg)
    return {
        "BackgroundNormal": bg,
        "BackgroundAlternate": blend(bg, fg, 0.10),
        "ForegroundNormal": fg,
        "ForegroundActive": fg,
        "ForegroundInactive": blend(fg, bg, 0.45),
        "ForegroundLink": readable_text_on(bg, light="#8fd0ff", dark="#2f6fb5"),
        "ForegroundVisited": readable_text_on(bg, light="#c9a6ff", dark="#6b4fbf"),
        "ForegroundPositive": readable_text_on(bg, light="#8fd98f", dark="#3f7a3a"),
        "ForegroundNeutral": readable_text_on(bg, light="#e8c07d", dark="#8a6320"),
        "ForegroundNegative": readable_text_on(bg, light="#f08f7d", dark="#a63f2c"),
        "DecorationFocus": blend(fg, bg, 0.20),
        "DecorationHover": blend(fg, bg, 0.40),
    }


def write_highlight_group(path: Path, colors: dict) -> bool:
    """Replace [Colors:Highlight] in a KDE .colors file, leaving the rest alone.

    The file is regenerated by kde-material-you-colors on every wallpaper
    change, so this is rewritten from scratch each time.
    """
    raw = path.read_text()

    block = "\n".join(f"{k}={v}" for k, v in colors.items())
    section = f"[{HIGHLIGHT_SECTION}]\n{block}\n"

    pattern = re.compile(
        rf"^\[{re.escape(HIGHLIGHT_SECTION)}\][^\[]*", re.MULTILINE | re.DOTALL
    )
    if pattern.search(raw):
        new_raw = pattern.sub(section, raw, count=1)
        new_raw = re.sub(r"\n{3,}", "\n\n", new_raw)
    else:
        new_raw = raw.rstrip("\n") + "\n\n" + section

    if new_raw == raw:
        print("[starship-matyou] panel highlight colors already up to date")
        return False

    path.write_text(new_raw)
    print(
        f"[starship-matyou] panel highlight set — bg {colors['BackgroundNormal']} "
        f"on text {colors['ForegroundNormal']} "
        f"(contrast {contrast_ratio(colors['ForegroundNormal'], colors['BackgroundNormal']):.1f}:1)"
    )
    return True


# ---------------------------------------------------------------------------
# Panel Colorizer
# ---------------------------------------------------------------------------


# How far the wallpaper hue is carried into the panel text, and into the panel
# background. Both keep only a trace of the hue so the result reads as clean
# near-white / near-black rather than a washed-out version of the wallpaper.
PANEL_TEXT_TINT = 0.90
PANEL_TEXT_DARK_TINT = 0.92
# The panel background is aimed at AAA rather than AA. Landing exactly on the
# 4.5:1 line leaves no headroom for the widget style's own text, which sits on
# this same surface and is not under our control.
PANEL_BG_CONTRAST = 7.0


def darken_tint(hex_color: str, against: list[str], min_ratio: float) -> str:
    """Darken hex_color, muting it in proportion to how far it had to go, until
    it clears min_ratio against every color in against.

    Muting per step is wrong in both directions. A pale wallpaper needs many steps
    to reach the target, so a per-step mute compounds and lands on flat grey —
    and the tint is the entire point. A saturated wallpaper that is already dark
    needs no steps at all and should keep its chroma. So the mute is applied once
    at the end, scaled by the total darkening, which makes the result consistent
    no matter how many steps a given color happened to need.
    """
    h0, s0, l0 = hex_to_hsl(hex_color)
    result = hex_color
    for _ in range(40):
        if all(contrast_ratio(result, other) >= min_ratio for other in against):
            break
        h, s, l = hex_to_hsl(result)
        result = hsl_to_hex(h, s, max(0.03, l - 0.03))

    h, s, l = hex_to_hsl(result)
    ratio = l / l0 if l0 else 1.0
    h, s = h, min(s, s0 * (0.35 + 0.65 * ratio))
    # Muting toward grey raises luminance, which can drop the contrast back under
    # the target. Keep darkening the muted color rather than falling back to the
    # unmuted one, which would defeat the point of muting it in the first place.
    l = max(0.03, l)
    for _ in range(20):
        candidate = hsl_to_hex(h, s, l)
        if all(contrast_ratio(candidate, other) >= min_ratio for other in against):
            return candidate
        l = max(0.03, l - 0.03)
    return hsl_to_hex(h, s, l)


def panel_background(p: dict) -> str:
    """Wallpaper-tinted panel background, normalized to the dark end.

    Panel Colorizer sets the panel background from the highlight color but never
    recolors the panel's own text (CustomBackground.qml returns early for
    `isPanel`), so that text stays whatever the Plasma widget style draws — a
    near-white. A light background therefore cannot be made legible at all.

    It also reverts items to the style color when window focus changes, without
    re-applying, which on a light panel is a visible flash between two very
    different colors. Darkening the panel makes the widget's color and the
    style's fallback agree, so the flash is invisible. The wallpaper hue
    survives, just at the dark end.
    """
    text = blend(p["primary"], "#ffffff", PANEL_TEXT_TINT)
    return darken_tint(p["primary"], [text], PANEL_BG_CONTRAST)


def panel_text_color(p: dict, bg: str) -> str:
    """Panel text: a light tint of the wallpaper hue, checked against bg.

    The panel is dark by construction, so light text is the default. `dark` is
    kept for anyone who has overridden the panel background to something light.
    """
    mode = str(SETTINGS.get("widget_text") or "auto").strip().lower()
    if mode == "dark":
        tint = blend(p["primary"], "#000000", PANEL_TEXT_DARK_TINT)
        return tint if contrast_ratio(tint, bg) >= MIN_CONTRAST else readable_text_on(bg)

    tint = blend(p["primary"], "#ffffff", PANEL_TEXT_TINT)
    if contrast_ratio(tint, bg) >= MIN_CONTRAST:
        return tint
    return readable_text_on(bg)


# KConfig section headers are written as [Containments][38][Applets][104]
# [Configuration][General]; splitting on the outer brackets leaves the name
# without its trailing "]", so match the suffix accordingly.
APPLET_GENERAL_SECTION = "[Configuration][General"


def update_panel_colorizer(p: dict) -> bool:
    """Write an explicit wallpaper text color into Panel Colorizer's widget config.

    By default Panel Colorizer draws widget text from `highlightedTextColor`, a
    palette lookup. That is the wrong shape here: the panel, the task manager and
    the application menu popup are different surfaces with different backgrounds,
    and one shared palette entry cannot be legible on all of them. Assigning the
    color directly (`sourceType` 0 = custom) decouples the text from the
    palette, so each surface can be given a tone that actually contrasts.
    """
    path = SETTINGS.get("panel_appletsrc")
    if not path or not path.exists():
        print(f"[starship-matyou] no panel appletsrc at {path}, skipping")
        return False

    bg = p["primary"]
    fg = panel_text_color(p, bg)
    raw = path.read_text()
    section = None
    out = []
    touched = 0

    for line in raw.splitlines():
        header = re.match(r"^\[(.+)\]$", line)
        if header:
            section = header.group(1)
        if (
            section
            and section.endswith(APPLET_GENERAL_SECTION)
            and line.startswith("globalSettings=")
        ):
            try:
                cfg = json.loads(line[len("globalSettings="):])
            except json.JSONDecodeError:
                out.append(line)
                continue
            normal = cfg.get("widgets", {}).get("normal")
            if isinstance(normal, dict):
                color = normal.setdefault("foregroundColor", {})
                desired = {
                    "enabled": True,
                    "sourceType": 0,
                    "custom": fg,
                    "alpha": 1,
                    "saturationEnabled": False,
                    "lightnessEnabled": False,
                }
                if any(color.get(k) != v for k, v in desired.items()):
                    color.update(desired)
                    touched += 1
                    line = "globalSettings=" + json.dumps(cfg, separators=(",", ":"))
        out.append(line)

    if not touched:
        print(f"[starship-matyou] panel widget text already {fg}")
        return False

    path.write_text("\n".join(out) + ("\n" if raw.endswith("\n") else ""))
    print(
        f"[starship-matyou] panel widget text -> {fg} "
        f"(wallpaper-derived, {contrast_ratio(fg, bg):.1f}:1 on panel {bg})"
    )
    return True


# ---------------------------------------------------------------------------
# Material You scheme reader
# ---------------------------------------------------------------------------

def find_active_scheme() -> Path | None:
    """Locate the .colors file Plasma is actually using.

    kde-material-you-colors also writes darker-titlebar and light variants
    alongside the active one, so prefer whatever kdeglobals points at. Writing
    colors into a variant nobody has selected is the kind of thing that looks
    like it worked and changes nothing.
    """
    if KDEGLOBALS.exists():
        cp = configparser.RawConfigParser(strict=False)
        cp.optionxform = str
        cp.read(KDEGLOBALS, encoding="utf-8")
        if cp.has_option("General", "ColorScheme"):
            name = cp.get("General", "ColorScheme").strip()
            candidate = COLOR_SCHEMES / f"{name}.colors"
            if candidate.exists():
                return candidate

    candidates = [
        COLOR_SCHEMES / "MaterialYouDark2.colors",
        COLOR_SCHEMES / "MaterialYouDark.colors",
        COLOR_SCHEMES / "MaterialYouLight2.colors",
        COLOR_SCHEMES / "MaterialYouLight.colors",
    ]
    for c in candidates:
        if c.exists():
            return c
    # fallback: any MaterialYou*.colors
    if COLOR_SCHEMES.exists():
        for f in sorted(COLOR_SCHEMES.glob("MaterialYou*.colors"), reverse=True):
            return f
    return None


def read_scheme(path: Path) -> configparser.RawConfigParser:
    cp = configparser.RawConfigParser()
    cp.read(path)
    return cp


def get_color(cp: configparser.RawConfigParser, group: str, key: str) -> str:
    val = cp.get(group, key)
    return strip_alpha(val)  # WM colors have #ff prefix


def extract_palette(cp: configparser.RawConfigParser) -> dict:
    """Return a dict of derived Material You roles from the KDE scheme."""
    p = {}
    p["primary"]       = get_color(cp, "Colors:Selection", "BackgroundNormal")
    p["onPrimary"]     = get_color(cp, "Colors:Selection", "ForegroundNormal")
    p["surfaceDim"]    = get_color(cp, "Colors:View",      "BackgroundNormal")
    p["onSurface"]     = get_color(cp, "Colors:View",      "ForegroundNormal")
    p["surfaceContainer"]     = get_color(cp, "Colors:Window",  "BackgroundNormal")
    p["surfaceContainerHigh"] = get_color(cp, "Colors:Button",  "BackgroundNormal")

    # WM colors: activeBackground = surfaceContainerHighest, inactive = secondaryContainer
    try:
        p["surfaceContainerHighest"] = get_color(cp, "WM", "activeBackground")
        _h, s, l = hex_to_hsl(p["surfaceContainerHighest"])
        # normalize: WM alpha-prefixed, sometimes the value is off
        # just use Button + slightly lighter if it looks off
        if l < 0.05:
            p["surfaceContainerHighest"] = set_lightness(p["surfaceContainerHigh"], 0.22)
    except Exception:
        p["surfaceContainerHighest"] = set_lightness(p["surfaceContainerHigh"], 0.22)

    try:
        p["secondaryContainer"] = get_color(cp, "WM", "inactiveBackground")
    except Exception:
        p["secondaryContainer"] = shift_hue(p["primary"], -20)

    # Derive tertiary: Material You triadic (+60° hue)
    p["tertiary"] = shift_hue(p["primary"], 60)

    # Derive secondary: same hue, lower chroma (desaturated primary)
    ph, ps, pl = hex_to_hsl(p["primary"])
    p["secondary"] = hsl_to_hex(ph, max(0.1, ps * 0.45), pl + 0.05 if pl < 0.5 else pl - 0.05)

    # Derive error: warm red (Material You standard error position ≈ hue 25°)
    p["error"] = hsl_to_hex(25, 0.85, 0.55)

    # Derived tones
    p["outline"] = blend(p["onSurface"], p["primary"], 0.25)
    p["onSurfaceVariant"] = set_lightness(p["onSurface"], 0.70)

    return p


# ---------------------------------------------------------------------------
# Starship palette builder
# ---------------------------------------------------------------------------

def ensure_contrast(
    hex_c: str, against: list[str], min_ratio: float, direction: str
) -> str:
    """Walk hex_c lighter or darker until it clears min_ratio against every color in against.

    Used instead of a flat minimum-lightness rule: the prompt's segments have
    fixed fg/bg pairings, so an accent has to clear contrast against the
    specific backgrounds it is drawn on, not against a guessed surface.
    """
    result = hex_c
    for _ in range(32):
        if all(contrast_ratio(result, other) >= min_ratio for other in against):
            return result
        h, s, l = hex_to_hsl(result)
        l = min(0.97, l + 0.03) if direction == "lighter" else max(0.03, l - 0.03)
        result = hsl_to_hex(h, s, l)
    return result


def build_starship_palette(p: dict) -> dict:
    """Map Material You roles → starship.toml palette keys.

    The gradient chain in the prompt is:
        black2 → green → blue2 → yellow → red → purple
    with fixed fg/bg pairings in starship.toml:

        black2  text: white3, green
        green   text: color_bg          arrow in: black2
        blue2   text: color_bg          arrow in: green
        yellow  text: color_bg          arrow in: blue2
        red     text: color_bg, red     arrow in: yellow
        purple  text: on-accent         arrow in: red

    Two of those pairings are wallpaper-dependent and will break on some
    wallpapers if the slots are left raw:

    - green/blue2/yellow carry `color_bg` text, so they must stay light enough
      to read against the window background.
    - purple is the wallpaper primary itself, so the text sitting on it cannot
      be a fixed slot — it is picked per wallpaper in `color_on_accent`.
    """
    primary = p["primary"]
    on_surface = p["onSurface"]
    surface = p["surfaceDim"]
    ph, ps, _pl = hex_to_hsl(primary)

    # Derive a "cool" base hue for the blue gradient — always 180° from primary
    cool_hue = (ph + 180) % 360

    # Ensure accent colors are readable (min lightness 0.62 on dark bg)
    def ensure_readable(hex_c: str, min_l: float = 0.62) -> str:
        h, s, l = hex_to_hsl(hex_c)
        return hsl_to_hex(h, s, max(l, min_l))

    # Segment backgrounds that carry `color_bg` text all need to read as light.
    # They are staggered rather than sharing one floor so the powerline arrow
    # between neighbouring segments still has a visible edge.
    green = ensure_contrast(
        ensure_readable(hsl_to_hex((ph + 150) % 360, min(0.7, ps + 0.1), 0.76), 0.76),
        [surface], MIN_CONTRAST, "lighter",
    )
    yellow = ensure_contrast(
        ensure_readable(hsl_to_hex((ph + 90) % 360, min(0.6, ps * 0.6), 0.80), 0.80),
        [surface], MIN_CONTRAST, "lighter",
    )
    blue2 = ensure_contrast(
        hsl_to_hex(cool_hue, 0.45, 0.64), [surface], MIN_CONTRAST, "lighter"
    )

    # red is drawn as text on top of yellow and blue2 (sudo, root username), so
    # it has to be dark — while still reading as a background for docker_context.
    red = ensure_contrast(
        hsl_to_hex(5, 0.80, 0.50), [yellow, blue2], MIN_CONTRAST, "darker"
    )

    # Text sitting on the wallpaper primary. Picked by contrast because a pale
    # wallpaper leaves near-white prompt text invisible.
    on_accent = readable_text_on(primary)

    # The dimmed variant for secondary text still has to clear AA, so fade it
    # toward the background only as far as the contrast budget allows. Stepping
    # the blend factor down (rather than nudging HSL lightness) is what makes
    # this hold on saturated mid-tones, where lightness and luminance diverge.
    on_accent_dim = on_accent
    for step in range(9, 0, -1):
        candidate = blend(on_accent, primary, step / 20)
        if contrast_ratio(candidate, primary) >= MIN_CONTRAST:
            on_accent_dim = candidate
            break

    return {
        # Main text / background
        "color_fg":    on_surface,
        "color_bg":    surface,

        # Surface gradient (dark → light, used for panel bg areas)
        "color_black1": p["surfaceDim"],
        "color_black2": p["surfaceContainer"],
        "color_black3": p["surfaceContainerHigh"],
        "color_black4": p["surfaceContainerHighest"],

        # Bright / white tones (for labels, highlights)
        "color_white1": on_surface,
        "color_white2": ensure_readable(set_lightness(on_surface, 0.78)),
        "color_white3": ensure_readable(p["outline"], 0.65),

        # Main accent palette
        "color_purple":  primary,
        "color_green":   green,
        "color_yellow":  yellow,
        "color_red":     red,
        "color_orange":  ensure_readable(hsl_to_hex((ph + 30) % 360, min(0.75, ps), 0.68)),

        # Text for the segments drawn on the wallpaper primary (git branch,
        # git status, directory). Recomputed per wallpaper.
        "color_on_accent":     on_accent,
        "color_on_accent_dim": on_accent_dim,

        # Blue gradient (cool-neutral, for subtle accents like username)
        "color_blue1": hsl_to_hex(cool_hue, 0.40, 0.30),
        "color_blue2": blue2,
        "color_blue3": hsl_to_hex(cool_hue, 0.40, 0.70),
        "color_blue4": hsl_to_hex(cool_hue, 0.35, 0.80),
    }


# ---------------------------------------------------------------------------
# Starship.toml updater
# ---------------------------------------------------------------------------

def format_palette_block(palette: dict) -> list[str]:
    """Return TOML lines for [palettes.material_you], wrapped in anchors."""
    order = [
        "color_fg", "color_bg",
        "color_red", "color_green", "color_yellow",
        "color_orange", "color_purple",
        "color_on_accent", "color_on_accent_dim",
        "color_white1", "color_white2", "color_white3",
        "color_black1", "color_black2", "color_black3", "color_black4",
        "color_blue1", "color_blue2", "color_blue3", "color_blue4",
    ]
    lines = ["# === material_you (auto-generated by starship-matyou.py) ===",
             "[palettes.material_you]"]
    for k in order:
        if k in palette:
            lines.append(f"{k} = '{palette[k]}'")
    lines.append("# === /material_you ===")
    return lines


PALETTE_START_ANCHOR = "# === material_you (auto-generated by starship-matyou.py) ==="
PALETTE_END_ANCHOR = "# === /material_you ==="


def update_starship(palette: dict) -> bool:
    if not STARSHIP_CFG.exists():
        print(f"[starship-matyou] starship.toml not found at {STARSHIP_CFG}", file=sys.stderr)
        return False

    content = STARSHIP_CFG.read_text()
    lines = content.split("\n")
    block = format_palette_block(palette)

    start = next((i for i, ln in enumerate(lines) if ln == PALETTE_START_ANCHOR), None)
    end = next((i for i, ln in enumerate(lines) if ln == PALETTE_END_ANCHOR), None)

    if start is not None and end is not None and end > start:
        lines[start:end + 1] = block
    else:
        # Insert before the first [palettes. table (COLORS section)
        for i, ln in enumerate(lines):
            if ln.startswith('[palettes.'):
                lines[i:i] = block
                break
        else:
            lines.extend(block)

    content = "\n".join(lines)

    # Ensure palette = 'material_you' is the active palette
    if re.search(r"^palette\s*=.*$", content, re.MULTILINE):
        content = re.sub(
            r"^palette\s*=.*$",
            "palette = 'material_you'",
            content,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        content = re.sub(
            r"(scan_timeout\s*=\s*\d+)",
            r"\1\n\npalette = 'material_you'",
            content,
            count=1,
        )

    STARSHIP_CFG.write_text(content)
    print(f"[starship-matyou] starship.toml updated")
    return True


# ---------------------------------------------------------------------------
# Fastfetch updater
# ---------------------------------------------------------------------------

def update_fastfetch(palette: dict) -> bool:
    if not FASTFETCH_CFG.exists():
        print(f"[starship-matyou] fastfetch config not found at {FASTFETCH_CFG}", file=sys.stderr)
        return False

    def ansi24(hex_color: str) -> str:
        """Convert hex to ANSI 24-bit foreground escape: '38;2;R;G;B'."""
        r, g, b = hex_to_rgb(hex_color)
        return f"38;2;{r};{g};{b}"

    primary_ansi = ansi24(palette["color_purple"])
    tertiary_ansi = ansi24(palette["color_green"])

    # Which accent each config section maps to:
    #   Software / header rows → primary, everything else → tertiary.
    software_sections = {"HEADER", "SOFTWARE"}
    hardware_sections = {"HARDWARE", "STORAGE", "MISC", "CUSTOMIZATION"}

    raw = FASTFETCH_CFG.read_text()
    lines = raw.split("\n")

    section = None
    changed = False

    for i, line in enumerate(lines):
        # Track current section from the comment markers
        m = re.search(r"// --- (\w+) ---", line)
        if m:
            section = m.group(1)
            continue

        # display.color.keys → primary, display.color.title → tertiary
        if '"keys":' in line and "38;2;" in line:
            new_line = re.sub(r'"keys":\s*"[^"]*"', f'"keys": "{primary_ansi}"', line)
        elif '"title":' in line and "38;2;" in line:
            new_line = re.sub(r'"title":\s*"[^"]*"', f'"title": "{tertiary_ansi}"', line)
        elif '"keyColor":' in line:
            color = primary_ansi if section in software_sections else tertiary_ansi
            new_line = re.sub(r'"keyColor":\s*"[^"]*"', f'"keyColor": "{color}"', line)
        else:
            continue

        if new_line != line:
            lines[i] = new_line
            changed = True

    if not changed:
        FASTFETCH_CFG.write_text(raw)
        print(f"[starship-matyou] fastfetch config.jsonc already up to date")
        return True

    FASTFETCH_CFG.write_text("\n".join(lines))
    print(f"[starship-matyou] fastfetch config.jsonc updated")
    return True


# ---------------------------------------------------------------------------
# Obsidian updater
# ---------------------------------------------------------------------------

def update_obsidian(palette: dict) -> bool:
    vault = SETTINGS["obsidian_vault"]
    if vault is None:
        print("[starship-matyou] obsidian skipped (no obsidian_vault configured)")
        return False

    cfg = vault / ".obsidian" / "appearance.json"
    if not cfg.exists():
        print(f"[starship-matyou] obsidian appearance.json not found at {cfg}", file=sys.stderr)
        return False

    raw = cfg.read_text()
    acc = palette["color_purple"]

    if re.search(r'"accentColor"\s*:', raw):
        new_raw = re.sub(
            r'"accentColor"\s*:\s*"[^"]*"',
            f'"accentColor": "{acc}"',
            raw,
            count=1,
        )
    else:
        # fall back to the alembic `accentColor` position (top of file, after {)
        new_raw = re.sub(
            r"^\{",
            f'{{ "accentColor": "{acc}",',
            raw,
            count=1,
        )

    if new_raw != raw:
        cfg.write_text(new_raw)
        print(f"[starship-matyou] obsidian accent color updated to {acc}")
        return True

    print(f"[starship-matyou] obsidian accent color already up to date ({acc})")
    return True


# ---------------------------------------------------------------------------
# Brave browser theme updater
# ---------------------------------------------------------------------------

# Chromium-family browsers (Brave included) watch /etc/brave/policies/managed/
# live and re-apply BrowserThemeColor instantly — no restart, no extension,
# no reloader plumbing. Brave derives the whole theme from this single color
# (same as its built-in "custom color" picker). That directory is system-level,
# so writing it needs root.
BRAVE_POLICY_FILE = "accent.json"


def to_dark_theme_color(color: str) -> str:
    """Clamp a wallpaper color into a dark, muted browser theme color.

    Chromium renders its toolbar/address bar from BrowserThemeColor directly:
    a light input produces a white-looking chrome, a dark input produces a dark
    one. Keep the wallpaper hue but force low lightness + low saturation.
    """
    h, s, _l = hex_to_hsl(color)
    return hsl_to_hex(h, min(s, 0.45), 0.28)


def update_brave(roles: dict) -> bool:
    policy_dir = SETTINGS["brave_policy_dir"]
    if policy_dir is None:
        print("[starship-matyou] brave skipped (no brave_policy_dir configured)")
        return False

    color = to_dark_theme_color(roles["primary"]).lower()
    new_raw = json.dumps({"BrowserThemeColor": color}, indent=2) + "\n"
    policy_file = policy_dir / BRAVE_POLICY_FILE

    if policy_file.exists() and policy_file.read_text() == new_raw:
        print("[starship-matyou] brave policy already up to date")
        return True

    try:
        policy_file.write_text(new_raw)
        print(f"[starship-matyou] brave policy updated → {color}")
        return True
    except OSError as e:
        print(f"[starship-matyou] brave policy write failed: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Contrast audit
# ---------------------------------------------------------------------------

def audit_prompt(palette: dict) -> int:
    """Report every fg/bg pair starship.toml actually draws that fails AA.

    The prompt's pairings are fixed in the config file while the colors behind
    them change with every wallpaper, so this is the only way to catch a bad
    combination before it shows up as invisible text in a terminal.
    """
    try:
        import tomllib
    except ModuleNotFoundError:
        print("[starship-matyou] audit needs Python 3.11+ for tomllib", file=sys.stderr)
        return 2

    if not STARSHIP_CFG.exists():
        print(f"[starship-matyou] audit needs {STARSHIP_CFG}", file=sys.stderr)
        return 2

    with STARSHIP_CFG.open("rb") as fh:
        config = tomllib.load(fh)

    pairs: list[tuple[str, str, str, str]] = []

    def record(where: str, style: str) -> None:
        fg = re.search(r"fg:(\S+)", style)
        bg = re.search(r"bg:(\S+)", style)
        if fg and bg:
            # In the main format the arrow glyphs are drawn as fg=previous
            # segment background on bg=next segment background. Those are seams,
            # not text, so they are reported but do not fail the audit.
            kind = "seam" if where in ("format", "right_format") else "text"
            pairs.append((where, fg.group(1), bg.group(1), kind))

    # Module styles, including the per-user variants starship supports.
    for module, body in config.items():
        if not isinstance(body, dict):
            continue
        for key in ("style", "style_user", "style_root"):
            if key in body and isinstance(body[key], str):
                record(f"{module}.{key}", body[key])

    # The main format string, where the arrow glyphs are drawn as fg=previous
    # segment background on bg=next segment background.
    for key in ("format", "right_format", "continuation_prompt"):
        body = config.get(key)
        if isinstance(body, str):
            for style in re.findall(r"\(([^()]*)\)", body):
                record(key, style)

    failures = 0
    for where, fg, bg, kind in pairs:
        fg_hex, bg_hex = palette.get(fg), palette.get(bg)
        if not fg_hex or not bg_hex:
            print(f"  ??   {where}: {fg} on {bg} — slot missing from palette")
            failures += 1
            continue
        ratio = contrast_ratio(fg_hex, bg_hex)
        if kind == "seam":
            print(f"  seam {where:22} {fg} on {bg}  {ratio:5.1f}:1")
            continue
        ok = ratio >= MIN_CONTRAST
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {where:22} {fg} on {bg}  {ratio:5.1f}:1")

    text_pairs = [p for p in pairs if p[3] == "text"]
    passed = sum(
        1
        for _, fg, bg, _ in text_pairs
        if palette.get(fg) and palette.get(bg)
        and contrast_ratio(palette[fg], palette[bg]) >= MIN_CONTRAST
    )
    print(
        f"\n  {passed}/{len(text_pairs)} text pairs pass WCAG AA "
        f"({MIN_CONTRAST}:1); seams listed above are decorative"
    )
    return 1 if failures else 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if "--check" in sys.argv:
        scheme_path = find_active_scheme()
        if not scheme_path:
            print("[starship-matyou] no Material You scheme found", file=sys.stderr)
            sys.exit(1)
        matyou = extract_palette(read_scheme(scheme_path))
        sys.exit(audit_prompt(build_starship_palette(matyou)))

    scheme_path = find_active_scheme()
    if not scheme_path:
        print("[starship-matyou] no Material You scheme found", file=sys.stderr)
        sys.exit(1)

    print(f"[starship-matyou] reading {scheme_path}")
    cp = read_scheme(scheme_path)
    matyou = extract_palette(cp)
    palette = build_starship_palette(matyou)

    # Show what we're working with
    print(f"  primary:    {matyou['primary']}")
    print(f"  tertiary:   {matyou['tertiary']}")
    print(f"  secondary:  {matyou['secondary']}")
    print(f"  surface:    {matyou['surfaceDim']}")
    print(f"  onSurface:  {matyou['onSurface']}")

    write_highlight_group(scheme_path, build_highlight_group(matyou))
    update_panel_colorizer(matyou)
    update_starship(palette)
    update_fastfetch(palette)
    update_obsidian(palette)
    update_brave(matyou)


if __name__ == "__main__":
    main()
