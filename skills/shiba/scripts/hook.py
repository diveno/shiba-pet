#!/usr/bin/env python3
"""
Hook di Claude Code per il cane: reazioni agli eventi e consigli periodici.

Due modi:
  hook.py react   PostToolUse su Bash — classifica il comando appena eseguito
                  (commit, push/apply = deploy, test verdi o rossi, errore) e
                  fa reagire il cane.
  hook.py tip     UserPromptSubmit — di tanto in tanto (cadenza gestita da
                  `shiba.py tip`) inietta un promemoria di igiene del lavoro.

Entrambi:
- escono SEMPRE con 0 e non stampano nulla quando non c'e' niente da dire: un
  hook che fallisce o che parla a ogni comando e' peggio di nessun hook;
- accendono il muso in statusline come effetto collaterale di `shiba.py`, che
  e' il posto dove il cane si vede davvero;
- restituiscono `additionalContext` cosi' la battuta arriva anche al modello,
  che puo' riportarla in una riga.
"""

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHIBA = os.path.join(HERE, "shiba.py")

# Corpo degli heredoc: va via prima di classificare. Un comando che scrive un
# file puo' contenere le parole "git commit" nel testo senza committare niente
# (succede scrivendo documentazione) e il cane festeggerebbe a vuoto.
HEREDOC = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?\n.*?^\s*\1\s*$",
    re.S | re.M,
)

# Posizione di comando: inizio stringa o subito dopo un separatore di shell.
# Senza questa ancora bastava la parola citata in mezzo a una frase.
CMD = r"(?:^|[;&|(\n]\s*|\$\(\s*)"

# Comando -> evento. Primo che matcha vince, quindi l'ordine conta:
# `terraform apply` prima di `terraform plan`.
RULES = [
    (CMD + r"git\s+commit\b", "commit"),
    (CMD + r"git\s+push\b", "deploy"),
    (CMD + r"terraform\s+apply\b", "deploy"),
    (CMD + r"terraform\s+plan\b", "apply"),
    (CMD + r"aws\s+ecs\s+update-service\b", "deploy"),
    (CMD + r"(\./)?[\w/-]*deploy[\w-]*\.sh\b", "deploy"),
    (CMD + r"(pytest|jest|vitest|phpunit|go\s+test)\b", "test"),
    (CMD + r"npm\s+(run\s+)?test\b", "test"),
    (CMD + r"(yarn|pnpm|bun)\s+(run\s+)?test\b", "test"),
    (CMD + r"(php\s+)?artisan\s+test\b", "test"),
]

# Indizi di test rossi nell'output. PostToolUse non passa il codice di uscita
# del comando, quindi l'esito si deduce da cio' che il comando ha stampato.
FAIL = re.compile(
    r"(\bFAIL(ED|URES?)?\b|\bfailed\b|\d+\s+failing\b|✕|✗|\bERRORS?\b)",
    re.I,
)


def run_shiba(*args):
    try:
        out = subprocess.run([sys.executable, SHIBA] + list(args),
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip()
    except Exception:
        return ""


def emit(event_name, text):
    if not text:
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": event_name,
        "additionalContext": text,
    }}))


def classify(command):
    command = HEREDOC.sub("<<STRIPPED", command)
    for pattern, event in RULES:
        if re.search(pattern, command, re.M):
            return event
    return None


def mode_react(payload):
    command = (payload.get("tool_input") or {}).get("command") or ""
    event = classify(command)
    if not event:
        return

    if event == "test":
        resp = payload.get("tool_response")
        blob = json.dumps(resp) if not isinstance(resp, str) else resp
        event = "tests-fail" if FAIL.search(blob or "") else "tests-pass"

    line = run_shiba("react", event, "--oneline")
    emit("PostToolUse", line)


def mode_tip(_payload):
    line = run_shiba("tip", "--oneline")
    emit("UserPromptSubmit", line)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "react"
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}
    try:
        (mode_tip if mode == "tip" else mode_react)(payload)
    except Exception:
        pass  # mai far fallire un hook per il cane


if __name__ == "__main__":
    main()
