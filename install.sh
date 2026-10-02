#!/usr/bin/env bash
#
# kde-rice installer
#
#   ./install.sh              deps + config + third-party components
#   ./install.sh --config     config files only
#   ./install.sh --extras     third-party components only
#   ./install.sh --deps       dependencies only
#   ./install.sh --no-backup  skip the timestamped backup
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="all"
BACKUP=1

for arg in "$@"; do
  case "$arg" in
    --config)    MODE="config" ;;
    --extras)    MODE="extras" ;;
    --deps)      MODE="deps" ;;
    --no-backup) BACKUP=0 ;;
    -h|--help)   sed -n '3,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

PLASMOID_DIR="$HOME/.local/share/plasma/plasmoids"
AURORAE_DIR="$HOME/.local/share/aurorae/themes"

# Installed from the fork, not PyPI: it carries the UltraVibrant scheme and the
# memoized HCT solver. Installing from PyPI makes every `pipx upgrade` silently
# drop those, because the venv is rebuilt from the upstream wheel.
KDE_MYOU_SRC="git+https://github.com/ooexiaoo/kde-material-you-colors.git"

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
info()  { printf '  %s\n' "$*"; }
fail()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# Resolve the download URL of a release asset matching a pattern.
# Prints nothing (and returns 1) when the repo or asset is gone.
latest_asset() {
  local repo="$1" pattern="$2"
  python3 - "$repo" "$pattern" <<'PY'
import json, sys, urllib.request
repo, pattern = sys.argv[1], sys.argv[2]
url = f"https://api.github.com/repos/{repo}/releases/latest"
try:
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.load(r)
except Exception:
    sys.exit(1)
for asset in data.get("assets", []):
    if pattern in asset["name"]:
        print(asset["browser_download_url"])
        sys.exit(0)
sys.exit(1)
PY
}

fetch() {
  local url="$1" dest="$2"
  mkdir -p "$(dirname "$dest")"
  curl -fsSL "$url" -o "$dest"
}

install_plasmoid() {
  local repo="$1" pattern="$2"
  local url
  url="$(latest_asset "$repo" "$pattern" || true)"
  if [ -z "$url" ]; then
    fail "no release asset matching '$pattern' in $repo — install it via System Settings > Get New Widgets"
  fi
  local tmp
  tmp="$(mktemp -d)"
  fetch "$url" "$tmp/widget.plasmoid"
  kpackagetool6 --type Plasma/Applet --install "$tmp/widget.plasmoid" >/dev/null
  rm -rf "$tmp"
  info "installed widget from $repo"
}

# ---------------------------------------------------------------------------
# Runtime dependencies
# ---------------------------------------------------------------------------
install_deps() {
  bold "Dependencies"

  if ! command -v pipx >/dev/null; then
    info "installing pipx"
    sudo dnf install -y pipx
    pipx ensurepath
  fi

  if ! command -v kde-material-you-colors >/dev/null; then
    info "installing kde-material-you-colors (the color backend, from the fork)"
    pipx install "$KDE_MYOU_SRC"
  else
    info "kde-material-you-colors already installed"
    info "to pull fork updates: pipx upgrade kde-material-you-colors"
  fi

  local missing=()
  command -v starship >/dev/null || missing+=(starship)
  command -v fastfetch >/dev/null || missing+=(fastfetch)
  command -v zsh     >/dev/null || missing+=(zsh)

  if [ "${#missing[@]}" -gt 0 ]; then
    info "installing: ${missing[*]}"
    sudo dnf install -y "${missing[@]}"
  else
    info "starship, fastfetch and zsh already installed"
  fi

  if [ ! -d "$HOME/.oh-my-zsh" ]; then
    info "installing oh-my-zsh"
    git clone -q https://github.com/oh-my-zsh/oh-my-zsh "$HOME/.oh-my-zsh"
  fi

  if ! fc-list | grep -qi "JetBrainsMono Nerd Font"; then
    info "installing JetBrainsMono Nerd Font (needed by Konsole and the prompt)"
    sudo dnf install -y 'nerd-fonts-jetbrains-mono-nerd-font-symbols'
  fi
}

# ---------------------------------------------------------------------------
# Config files
# ---------------------------------------------------------------------------
install_config() {
  bold "Config files"

  if [ "$BACKUP" -eq 1 ]; then
    local stamp
    stamp="$(date +%Y%m%d-%H%M%S)"
    local backed=0
    for path in .config .zshrc; do
      if [ -e "$HOME/$path" ]; then
        cp -a "$HOME/$path" "$HOME/${path}.bak-$stamp"
        backed=1
      fi
    done
    [ "$backed" -eq 1 ] && info "backed up existing files to ~/*$(printf '.bak-%s' "$stamp")"
  fi

  rsync -a "$REPO_DIR/.config/" "$HOME/.config/"
  cp "$REPO_DIR/.zshrc" "$HOME/.zshrc"
  chmod +x "$HOME/.config/starship-matyou.py"
  info "copied .config/ and .zshrc"

  if [ ! -e "$HOME/.config/starship-matyou.conf" ]; then
    cp "$REPO_DIR/starship-matyou.conf.example" "$HOME/.config/starship-matyou.conf"
    info "created ~/.config/starship-matyou.conf (Obsidian/Brave targets are off by default)"
  fi
}

# ---------------------------------------------------------------------------
# Third-party components
# ---------------------------------------------------------------------------
install_extras() {
  bold "Third-party components"

  command -v kpackagetool6 >/dev/null || fail "kpackagetool6 not found — install the plasma-workspace tools for your distro"

  # Aurorae window decoration: titlebar-free, active window in the accent color
  if [ -d "$AURORAE_DIR/ActiveAccentFrame" ]; then
    info "ActiveAccent already present"
  else
    local tmp
    tmp="$(mktemp -d)"
    git clone -q --depth 1 https://github.com/nclarius/Plasma-window-decorations "$tmp/pwd"
    cp -a "$tmp/pwd/ActiveAccentFrame" "$AURORAE_DIR/"
    rm -rf "$tmp"
    info "installed ActiveAccentFrame decoration (GPL-3.0, Natalie Clarius)"
  fi

  # KWin tiling script
  local krohnkite_url
  krohnkite_url="$(curl -fsSL "https://codeberg.org/api/v1/repos/anametologin/Krohnkite/releases?limit=1" 2>/dev/null |
    python3 -c 'import json,sys
try:
    assets = json.load(sys.stdin)[0]["assets"]
except Exception:
    sys.exit(1)
for a in assets:
    if a["name"] == "krohnkite.kwinscript":
        print(a["browser_download_url"]); break' || true)"
  if [ -z "$krohnkite_url" ]; then
    info "SKIPPED Kröhnkite — no .kwinscript found, see https://codeberg.org/anametologin/Krohnkite"
  else
    local tmp
    tmp="$(mktemp -d)"
    fetch "$krohnkite_url" "$tmp/krohnkite.kwinscript"
    kpackagetool6 --type KWin/Script --install "$tmp/krohnkite.kwinscript" >/dev/null
    rm -rf "$tmp"
    info "installed Kröhnkite KWin tiling script"
  fi

  # Panel widgets referenced by the shipped panel layout
  install_plasmoid luisbocanegra/plasma-panel-colorizer  "plasmoid-panel-colorizer"
  install_plasmoid luisbocanegra/plasma-panel-spacer-extended "plasmoid-spacer-extended"

  # Virtual-desktop pager
  local mike_url
  mike_url="$(latest_asset codelovesme/mike-desktop "mike-desktop" || true)"
  if [ -z "$mike_url" ]; then
    info "SKIPPED Mike Desktop — no release asset found"
  else
    local tmp
    tmp="$(mktemp -d)"
    fetch "$mike_url" "$tmp/mike.tar.gz"
    tar -xzf "$tmp/mike.tar.gz" -C "$tmp"
    cp -a "$tmp"/*/ "$PLASMOID_DIR/" 2>/dev/null || cp -a "$tmp"/. "$PLASMOID_DIR/"
    rm -rf "$tmp"
    info "installed Mike Desktop virtual-desktop pager"
  fi
}

# ---------------------------------------------------------------------------
case "$MODE" in
  config) install_config ;;
  extras) install_extras ;;
  deps)   install_deps ;;
  all)    install_deps; install_config; install_extras ;;
esac

cat <<'EOF'

Next steps
----------
  1. Install the color backend and the Material You widget:
       pipx install git+https://github.com/ooexiaoo/kde-material-you-colors.git
     then add "KDE Material You Colors" to your panel via
     System Settings, or the KDE Store (https://store.kde.org/p/2136963).
     Upgrade it with `pipx upgrade kde-material-you-colors` -- it tracks the
     fork, so the local patches survive.

  2. Set a wallpaper. The shipped appletsrc intentionally has no wallpaper
     path, so Plasma keeps whatever you already had. Changing it is what
     triggers the whole color pipeline.

  3. Point your Obsidian vault at the script if you want it themed:
       cp ~/.config/starship-matyou.conf.example ~/.config/starship-matyou.conf
     then uncomment obsidian_vault.

  4. Restart the shell and reload KWin, then log out and back in so the
     new widgets and the KWin script are picked up:
       exec zsh
       kwin_wayland --replace &
EOF
