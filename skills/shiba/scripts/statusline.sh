#!/bin/sh
# Status line: keeps an existing one and appends the dog's rows.
#
# Set SHIBA_STATUSLINE_BASE to the command of the status line you already use
# (for example: export SHIBA_STATUSLINE_BASE="npx -y ccstatusline@latest") and
# its output is printed first. The two parts are independent: if one fails the
# other still prints.
here=$(dirname "$0")
input=$(cat)

if [ -n "$SHIBA_STATUSLINE_BASE" ]; then
  base=$(printf '%s' "$input" | sh -c "$SHIBA_STATUSLINE_BASE" 2>/dev/null)
  [ -n "$base" ] && printf '%s\n' "$base"
fi

printf '%s' "$input" | python3 "$here/statusline.py" 2>/dev/null
