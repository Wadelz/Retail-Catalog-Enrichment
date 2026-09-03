#!/usr/bin/env bash
# Drive a nested interactive Claude Code CLI running in a tmux pty.
#
# A web/SDK session talks over --input-format=stream-json with no TTY on stdin
# or stdout, so anything gated on an interactive session refuses to run there.
# A second `claude` inside a tmux pty has a real TTY and does not.
set -uo pipefail

SESSION="${NESTED_TMUX_SESSION:-nested-claude}"
PROJECT_DIR="${NESTED_PROJECT_DIR:-$PWD}"
COLS="${NESTED_COLS:-200}"
ROWS="${NESTED_ROWS:-50}"

die() { echo "error: $*" >&2; exit 1; }
have_session() { tmux has-session -t "$SESSION" 2>/dev/null; }
require_session() { have_session || die "no session '$SESSION'; run: nested.sh start"; }
pane() { tmux capture-pane -t "$SESSION" -p 2>/dev/null; }

# A modal is up when the pane is asking something. Each pattern below is a real
# prompt seen in practice, not a guess: permission prompts, the first-run theme
# picker, the login-method chooser, and the OAuth code field.
pane_blocked() {
  # "Enter to confirm" is the reliable marker: every modal select prints it,
  # numbered or not. Matching a bare "❯ " instead would false-positive on the
  # ordinary input line, which uses the same glyph.
  pane | grep -qE "Do you want to proceed\?|Select login method:|Paste code here|To change this later, run /theme|Enter to confirm|Is this a project you created|❯ +[0-9]+\."
}

pane_busy() {
  pane | grep -qiE "esc to interrupt|✢|✳|∴|Mulling|Thinking|Working"
}

cmd_start() {
  local mode=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --permission-mode) [ $# -ge 2 ] || die "--permission-mode needs a value"; mode="$2"; shift ;;
      --permission-mode=*) mode="${1#*=}" ;;
      --dir) [ $# -ge 2 ] || die "--dir needs a value"; PROJECT_DIR="$2"; shift ;;
      *) die "unknown option '$1'" ;;
    esac
    shift
  done
  case "$mode" in ""|acceptEdits|auto|bypassPermissions|dontAsk|plan|manual) ;;
    *) die "unknown permission mode '$mode'" ;; esac
  [ "$mode" = "plan" ] && echo "warning: 'plan' waits for a human approval this driver cannot give"

  have_session && { echo "session '$SESSION' already running; use status or kill"; return 0; }

  local mode_arg=""; [ -n "$mode" ] && mode_arg=" --permission-mode $mode"

  # Two things are load-bearing here.
  #
  # 1. No stdout redirection. Piping claude's stdout (| tee, > log) makes it
  #    detect a non-TTY and fall back to --print mode, which exits immediately
  #    with "Input must be provided either through stdin or as a prompt
  #    argument" -- defeating the entire point of using a pty. For a log use
  #    `tmux pipe-pane`, which preserves the pty.
  #
  # 2. Strip the host's auth plumbing. Inherited, PROVIDER_MANAGED_BY_HOST and
  #    the token file descriptors make the nested process look for a token on
  #    an fd that does not exist in it, so every request fails Authentication
  #    error even with valid stored credentials. Unsetting the session-ID vars
  #    additionally stops the child from renaming the parent's task directory
  #    out from under it.
  tmux new-session -d -s "$SESSION" -c "$PROJECT_DIR" -x "$COLS" -y "$ROWS" "env \
    -u CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST \
    -u CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR \
    -u CLAUDE_CODE_WEBSOCKET_AUTH_FILE_DESCRIPTOR \
    -u CLAUDE_CODE_POST_FOR_SESSION_INGRESS_V2 \
    -u CLAUDE_SESSION_INGRESS_TOKEN_FILE \
    -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN \
    -u CLAUDE_CODE_REMOTE -u CLAUDE_CODE_CHILD_SESSION -u CLAUDE_CODE_ENTRYPOINT \
    -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_REMOTE_SESSION_ID -u CLAUDECODE \
    -u CLAUDE_CODE_DIAGNOSTICS_FILE -u CLAUDE_PID \
    claude$mode_arg" || die "tmux launch failed"

  echo "launched '$SESSION' in $PROJECT_DIR"
  echo "first run shows theme -> login -> trust prompts; check with: nested.sh status"
}

cmd_status() {
  require_session
  echo "=== tmux ==="
  tmux list-panes -t "$SESSION" -F "session=$SESSION dead=#{pane_dead} cmd=#{pane_current_command}" 2>/dev/null
  if pane_blocked; then echo "STATE: BLOCKED on a prompt — read the pane, then approve or keys"
  elif pane_busy;  then echo "STATE: WORKING"
  else                  echo "STATE: idle"; fi
  echo
  echo "=== pane (last 20 lines) ==="
  pane | grep -vE '^\s*$' | tail -20
}

cmd_send() {
  [ $# -gt 0 ] || die "usage: nested.sh send <text>"
  require_session
  pane_blocked && die "pane is blocked on a prompt; resolve it with approve/keys first"
  # -l sends the text literally so punctuation is never read as a key name.
  tmux send-keys -t "$SESSION" -l "$*"
  sleep 0.4
  tmux send-keys -t "$SESSION" Enter
  echo "sent: $*"
}

cmd_keys() {
  [ $# -gt 0 ] || die "usage: nested.sh keys <text|KeyName>"
  require_session
  case "$1" in
    Enter|Escape|Tab|Up|Down|Left|Right|Space|BSpace|C-c|C-d|C-o)
      tmux send-keys -t "$SESSION" "$1" ;;
    *) tmux send-keys -t "$SESSION" -l "$*" ;;
  esac
  echo "keys sent: $*"
}

cmd_approve() {
  require_session
  pane_blocked || { echo "nothing appears to be blocking; not sending Enter"; return 0; }
  tmux send-keys -t "$SESSION" Enter
  echo "confirmed the highlighted option"
}

# The input line renders placeholder/suggestion text that is NOT buffer content:
# `clear` and Escape both no-op against it, and typing REPLACES it. To tell them
# apart, type a character and see whether it appends or replaces.
cmd_clear() {
  require_session
  tmux send-keys -t "$SESSION" C-u
  echo "input line cleared (placeholder text may still render — that is not buffer content)"
}

cmd_login_url() {
  require_session
  pane | tr -d '\n' | grep -oE 'https://claude\.com/[^ ]*' | head -1 \
    || echo "no login URL on screen; run: nested.sh status"
}

# Wait on a condition, never a fixed sleep. Bails early when the pane blocks,
# since no amount of waiting clears a modal.
cmd_wait() {
  require_session
  local want="${1:-idle}" limit="${2:-300}" waited=0
  while [ "$waited" -lt "$limit" ]; do
    case "$want" in
      idle)    pane_blocked && { echo "BLOCKED after ${waited}s"; return 2; }
               pane_busy   || { echo "IDLE after ${waited}s"; return 0; } ;;
      blocked) pane_blocked && { echo "BLOCKED after ${waited}s"; return 0; } ;;
      *) die "usage: nested.sh wait [idle|blocked] [seconds]" ;;
    esac
    sleep 5; waited=$((waited + 5))
  done
  echo "timed out after ${limit}s waiting for '$want'"; return 1
}

cmd_kill() {
  have_session || { echo "no session '$SESSION'"; return 0; }
  tmux kill-session -t "$SESSION" 2>/dev/null
  echo "killed '$SESSION'"
}

case "${1:-}" in
  start)     shift; cmd_start "$@" ;;
  status)    cmd_status ;;
  send)      shift; cmd_send "$@" ;;
  keys)      shift; cmd_keys "$@" ;;
  approve)   cmd_approve ;;
  clear)     cmd_clear ;;
  login-url) cmd_login_url ;;
  wait)      shift; cmd_wait "$@" ;;
  kill)      cmd_kill ;;
  *) cat <<USAGE
usage: nested.sh <command>

  start [--permission-mode M] [--dir D]  launch the nested session
  status                                 tmux state + pane tail
  send <text>                            type a prompt and submit it
  keys <text|KeyName>                    raw passthrough (Enter, Escape, Up, ...)
  approve                                press Enter on a blocking prompt
  clear                                  empty a stranded input line
  login-url                              print the OAuth URL from the pane
  wait [idle|blocked] [secs]             block until a condition holds
  kill                                   terminate the session
USAGE
    exit 2 ;;
esac
