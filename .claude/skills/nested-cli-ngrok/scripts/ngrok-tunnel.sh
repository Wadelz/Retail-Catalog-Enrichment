#!/usr/bin/env bash
# Install ngrok, connect a tunnel, and report the public URL.
#
# The container is unreachable from outside: it has no public inbound address,
# so anything listening here is invisible to the user's browser and to any
# service that needs to call back in. A tunnel is the fix.
set -uo pipefail

NGROK_BIN="${NGROK_BIN:-/usr/local/bin/ngrok}"
NGROK_LOG="${NGROK_LOG:-/tmp/ngrok.log}"
NGROK_API="http://127.0.0.1:4040/api/tunnels"
DL_URL="${NGROK_DOWNLOAD_URL:-https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz}"

die() { echo "error: $*" >&2; exit 1; }
installed() { [ -x "$NGROK_BIN" ]; }

cmd_install() {
  if installed; then echo "already installed: $("$NGROK_BIN" version 2>&1 | head -1)"; return 0; fi
  local tmp; tmp=$(mktemp -d)
  echo "downloading ngrok…"
  curl -sSL --max-time 300 "$DL_URL" -o "$tmp/ngrok.tgz" || die "download failed"
  tar xzf "$tmp/ngrok.tgz" -C "$tmp" || die "extract failed (is the download an HTML error page?)"
  install -m 0755 "$tmp/ngrok" "$NGROK_BIN" || die "install to $NGROK_BIN failed"
  rm -rf "$tmp"
  echo "installed: $("$NGROK_BIN" version 2>&1 | head -1)"
}

cmd_auth() {
  installed || die "not installed; run: ngrok-tunnel.sh install"
  # Never accept the token as a positional argument: it would land in the shell
  # history and in `ps` output for every process on the box. Read it from the
  # environment, which the caller sets out of band.
  local token="${NGROK_AUTHTOKEN:-}"
  [ -n "$token" ] || die "set NGROK_AUTHTOKEN in the environment first (get one at https://dashboard.ngrok.com/get-started/your-authtoken)"
  "$NGROK_BIN" config add-authtoken "$token" >/dev/null 2>&1 || die "add-authtoken failed"
  echo "authtoken configured (value not echoed)"
}

cmd_start() {
  local port="${1:?usage: ngrok-tunnel.sh start <port>}"
  installed || die "not installed; run: ngrok-tunnel.sh install"
  if curl -sf --max-time 3 --noproxy '*' "$NGROK_API" >/dev/null 2>&1; then
    echo "a tunnel is already running; use 'url' or 'stop'"; return 0
  fi
  # --log=stdout keeps the agent in the foreground of this background job so
  # its errors are captured. ngrok is not a TTY program, so redirecting its
  # output is safe here -- unlike the nested claude CLI, which must never be
  # redirected.
  nohup "$NGROK_BIN" http "$port" --log=stdout > "$NGROK_LOG" 2>&1 &
  echo "starting tunnel to :$port (log: $NGROK_LOG)"
  local waited=0
  while [ "$waited" -lt 40 ]; do
    if curl -sf --max-time 3 --noproxy '*' "$NGROK_API" >/dev/null 2>&1; then
      cmd_url; return 0
    fi
    if grep -qiE "ERR_NGROK|authentication failed|ERR_NGROK_105|command failed" "$NGROK_LOG" 2>/dev/null; then
      echo "ngrok failed to start:"; grep -iE "ERR_NGROK|err=|msg=" "$NGROK_LOG" | tail -5; return 2
    fi
    sleep 2; waited=$((waited + 2))
  done
  echo "tunnel did not come up within 40s; last log lines:"; tail -8 "$NGROK_LOG"; return 1
}

cmd_url() {
  local body
  body=$(curl -sf --max-time 10 --noproxy '*' "$NGROK_API" 2>/dev/null) \
    || die "no local ngrok API on :4040 — is the tunnel running?"
  echo "$body" | python3 -c '
import json,sys
d=json.load(sys.stdin)
ts=d.get("tunnels") or []
if not ts:
    print("no active tunnels"); raise SystemExit(1)
for t in ts:
    print(f'"'"'{t["public_url"]}  ->  {t["config"]["addr"]}'"'"')
'
}

cmd_status() {
  echo "binary:  $(installed && "$NGROK_BIN" version 2>&1 | head -1 || echo 'NOT INSTALLED')"
  echo -n "auth:    "; [ -f "$HOME/.config/ngrok/ngrok.yml" ] && echo "configured" || echo "no authtoken configured"
  echo -n "tunnel:  "
  if curl -sf --max-time 5 --noproxy '*' "$NGROK_API" >/dev/null 2>&1; then cmd_url; else echo "not running"; fi
}

cmd_stop() {
  local pids; pids=$(ps aux 2>/dev/null | grep "[n]grok http" | awk '{print $2}')
  # Kill by PID. `pkill -f ngrok` also matches the shell running this very
  # command and kills it mid-script, which reads as an unexplained exit 143.
  [ -n "$pids" ] || { echo "no ngrok process running"; return 0; }
  for p in $pids; do kill "$p" 2>/dev/null && echo "stopped pid $p"; done
}

case "${1:-}" in
  install) cmd_install ;;
  auth)    cmd_auth ;;
  start)   shift; cmd_start "$@" ;;
  url)     cmd_url ;;
  status)  cmd_status ;;
  stop)    cmd_stop ;;
  *) cat <<USAGE
usage: ngrok-tunnel.sh <command>

  install        download and install the ngrok binary
  auth           configure the authtoken from \$NGROK_AUTHTOKEN
  start <port>   open a tunnel to a local port and print the public URL
  url            print the current public URL(s)
  status         binary / auth / tunnel state
  stop           terminate the running tunnel
USAGE
    exit 2 ;;
esac
