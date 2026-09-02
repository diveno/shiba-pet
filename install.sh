#!/bin/sh
# Installer for the parts a Claude Code plugin cannot set up by itself:
# the `mochi` command and the status line. The skill and the hooks come with
# the plugin - see README.md.
#
#   ./install.sh                 command + status line (asks first)
#   ./install.sh --bin-only      only the mochi command
#   ./install.sh --lang it       pick the dog's language (en, it)
#   BIN=~/bin ./install.sh       install the command elsewhere
set -e

HERE=$(cd "$(dirname "$0")" && pwd)
BIN=${BIN:-$HOME/.local/bin}
SETTINGS=$HOME/.claude/settings.json
LANG_CODE=en
BIN_ONLY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --bin-only) BIN_ONLY=1 ;;
    --lang) LANG_CODE=$2; shift ;;
    *) echo "unknown option: $1"; exit 1 ;;
  esac
  shift
done

command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
[ -f "$HERE/skills/shiba/i18n/$LANG_CODE.json" ] || {
  echo "unknown language: $LANG_CODE (available: $(ls "$HERE/skills/shiba/i18n" | sed 's/\.json//' | tr '\n' ' '))"
  exit 1
}

# --- the mochi command --------------------------------------------------
mkdir -p "$BIN"
cat > "$BIN/mochi" <<EOF
#!/bin/sh
# Shortcut for the CLI shiba. The logic lives in the skill (see \`mochi help\`).
exec python3 "$HERE/skills/shiba/scripts/shiba.py" "\$@"
EOF
chmod +x "$BIN/mochi"
echo "installed: $BIN/mochi"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "  note: $BIN is not on your PATH - add it to your shell profile" ;;
esac

# --- first run, so the state exists with the chosen language ------------
SHIBA_LANG=$LANG_CODE python3 "$HERE/skills/shiba/scripts/shiba.py" lang "$LANG_CODE" --oneline

[ "$BIN_ONLY" = "1" ] && exit 0

# --- status line --------------------------------------------------------
printf 'Wire the status line into %s? [y/N] ' "$SETTINGS"
read -r answer
case "$answer" in
  y|Y|yes)
    python3 - "$SETTINGS" "$HERE" <<'PY'
import json, os, shutil, sys
settings, here = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(settings), exist_ok=True)
data = {}
if os.path.exists(settings):
    shutil.copy(settings, settings + ".bak-shiba")
    try:
        data = json.load(open(settings))
    except ValueError:
        print("  %s is not plain JSON (comments?) - add this by hand:" % settings)
        print('  "statusLine": {"type": "command", "command": "sh %s/skills/shiba/scripts/statusline.sh"}' % here)
        raise SystemExit(0)
old = (data.get("statusLine") or {}).get("command")
if old and "shiba" not in old:
    print("  keeping your current status line, chained via SHIBA_STATUSLINE_BASE:")
    print("    export SHIBA_STATUSLINE_BASE=%r" % old)
data["statusLine"] = {"type": "command",
                      "command": "sh %s/skills/shiba/scripts/statusline.sh" % here,
                      "padding": 0, "refreshInterval": 10}
json.dump(data, open(settings, "w"), indent=2, ensure_ascii=False)
print("  status line wired (backup: %s.bak-shiba)" % settings)
PY
    ;;
  *) echo "  skipped - see README.md for the manual snippet" ;;
esac

echo
echo "Done. Try:  mochi        (or 'mochi help')"
echo "Reactions to commits, deploys and tests come with the plugin:"
echo "  /plugin marketplace add <owner>/shiba-pet && /plugin install shiba"
