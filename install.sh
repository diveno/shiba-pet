#!/bin/sh
# Installer for the parts a Claude Code plugin cannot set up by itself:
# the `shiba` command and the status line. The skill and the hooks come with
# the plugin - see README.md.
#
#   ./install.sh                 command + status line (asks first)
#   ./install.sh --bin-only      only the shiba command
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

# --- the shiba command --------------------------------------------------
mkdir -p "$BIN"
cat > "$BIN/shiba" <<EOF
#!/bin/sh
# Shortcut for the CLI shiba. The logic lives in the skill (see \`shiba help\`).
exec python3 "$HERE/skills/shiba/scripts/shiba.py" "\$@"
EOF
chmod +x "$BIN/shiba"
echo "installed: $BIN/shiba"
# Up to 1.0.0 the command was named after the default dog - but the name is
# renameable and the command is not, so it moved to `shiba`. The old shim still
# works; it is the user's to delete.
if [ -f "$BIN/mochi" ] && grep -q "skills/shiba/scripts/shiba.py" "$BIN/mochi" 2>/dev/null; then
  echo "  note: the old $BIN/mochi still works - remove it when you like"
fi
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
import json, os, shlex, shutil, sys
settings, here = sys.argv[1], sys.argv[2]


def open_or_empty(path):
    try:
        return open(path).read()
    except IOError:
        return ""


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
# Whatever was there before has to survive the swap. Three shapes: nothing,
# someone else's status line (chain it in front of the dog's), or a wrapper of
# ours from an earlier install - there, keep the environment already wired and
# only move the path, or a re-run would silently drop the chained base.
old = (data.get("statusLine") or {}).get("command") or ""
mine = "skills/shiba/scripts/statusline.sh"
if mine in old:
    env = old[:old.rfind("sh ")]          # the last `sh ` starts our own call
    prev = old[old.rfind("sh ") + 3:].strip()
    if "SHIBA_STATUSLINE_BASE" not in env:
        # An old wrapper could carry its base hardcoded rather than read it
        # from the environment: that is invisible here, so say what is in it.
        for ln in open_or_empty(os.path.expanduser(prev)).splitlines():
            if "base=" in ln and "SHIBA_STATUSLINE_BASE" not in ln:
                print("  heads up: the wrapper you are replacing ran its own base command")
                print("    %s" % ln.strip())
                print("  re-add it with SHIBA_STATUSLINE_BASE to keep it")
                break
elif old:
    print("  keeping your current status line, chained in front of the dog's")
    env = "SHIBA_STATUSLINE_BASE=%s " % shlex.quote(old)
else:
    env = ""
data["statusLine"] = {"type": "command",
                      "command": env + "sh %s/%s" % (here, mine),
                      "padding": 0, "refreshInterval": 10}
json.dump(data, open(settings, "w"), indent=2, ensure_ascii=False)
print("  status line wired (backup: %s.bak-shiba)" % settings)
PY
    ;;
  *) echo "  skipped - see README.md for the manual snippet" ;;
esac

echo
echo "Done. Try:  shiba        (or 'shiba help')"
echo "Reactions to commits, deploys and tests come with the plugin:"
echo "  /plugin marketplace add diveno/shiba-pet && /plugin install shiba"
