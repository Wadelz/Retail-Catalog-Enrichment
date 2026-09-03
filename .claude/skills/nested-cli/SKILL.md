---
name: nested-cli
description: Open and drive a nested interactive Claude Code CLI inside this container over tmux. Use whenever something needs a real TTY that a web or SDK session cannot provide — spawning agent teams, walking an interactive login, driving a slash-command flow — or when the user says "start a nested CLI", "open a second Claude", "spawn teammates", "why won't agent teams work here", or asks to message, inspect or stop such a session.
---

# Driving a nested Claude Code CLI

## Why this exists

Claude Code gates some features on an **interactive** session, and "interactive"
means the process's I/O mode, not whether a human is typing. A web or SDK
session runs `--input-format=stream-json` with no TTY on stdin or stdout, so it
fails that check even though a person is clearly at the other end. No settings
key opens the gate: the mode is fixed by the launch command before any settings
file is read.

The way through is to launch a *second* `claude` inside a tmux pty in the same
container. That process has a real TTY, so the gate opens, and this session
drives it with `tmux send-keys` / `capture-pane`.

Everything routes through `scripts/nested.sh`. Prefer it over ad-hoc tmux calls:
it encodes the failure modes below, each of which costs real time to rediscover.

## Commands

```bash
bash scripts/nested.sh <command>
```

| Command | What it does |
| --- | --- |
| `start [--permission-mode M] [--dir D]` | Launch the nested session with the right environment |
| `status` | tmux state, blocked/working/idle, pane tail |
| `send <text>` | Type a prompt and submit it |
| `keys <text\|KeyName>` | Raw passthrough (`Enter`, `Escape`, `Up`, `Tab`, `C-c`) |
| `approve` | Press Enter on a blocking prompt |
| `clear` | Empty a stranded input line |
| `login-url` | Print the OAuth URL currently on screen |
| `wait [idle\|blocked] [secs]` | Block until a condition holds |
| `kill` | Terminate the session |

Report results in prose. The user cannot see the pane, so summarise what
changed rather than pasting terminal dumps — and say explicitly when the pane is
blocked, because from their side a blocked pane and a slow one look identical.

## Getting through first-run

A fresh container has no stored credentials, so `start` lands in a sequence of
prompts. Walk them in order:

1. **Theme picker.** `approve` may not classify this as blocking on every build;
   `keys Enter` always works.
2. **Login method.** Option 1 (subscription) is preselected. `keys Enter`.
3. **OAuth.** The pane prints a URL and waits at `Paste code here`. Run
   `login-url`, give the URL to the user, and ask them to send back the code.
   Deliver it with `keys <code>` then `keys Enter`.
4. **Folder trust**, if it appears. `approve`.

The authorization code is short-lived and single-use, so passing it through the
conversation is bounded exposure — but say so rather than asking for it silently.
An API key would be long-lived and is a different matter; prefer the env-var
route for those.

## Failure modes worth knowing

**Never redirect the nested session's stdout.** A `| tee` or `> log` makes
Claude Code detect a non-TTY stdout, fall back to `--print` mode, and exit with
`Input must be provided either through stdin or as a prompt argument`. That
defeats the entire purpose. For a log, use `tmux pipe-pane`, which preserves the
pty.

**Strip the host's auth plumbing at launch.** Inherited,
`CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST` and the OAuth/websocket token *file
descriptors* make the child look for a token on an fd that does not exist in its
own process, so every request fails `Authentication error` even with perfectly
good stored credentials. `start` unsets these.

**Unset the session-ID variables too.** Otherwise the child inherits this
session's UUID and can rename `~/.claude/tasks/<uuid>/` out from under the
still-running parent, whose task list then reports zero tasks. If a parent task
list goes mysteriously empty, this is why, and the records are intact under the
other name.

**A blocked pane looks exactly like a slow one.** `status` distinguishes them,
and `send` refuses to type into a blocked pane rather than firing keystrokes
into a modal.

**Placeholder text is not buffer content.** The input line renders suggestion
text that `clear` and `Escape` both no-op against, because there is nothing in
the buffer to clear. To tell placeholder from real stranded input, type a
character: if it *replaces* the line it was a placeholder, if it *appends* the
text is real. Do not conclude a command is queued just because it renders.

**Wait on conditions, never fixed sleeps.** Use `wait`, ideally with the Bash
tool's `run_in_background: true` so a long wait does not block a foreground
call. It bails out early when the pane blocks, since waiting never clears a
modal.

**Killing the process needs a PID, not a pattern.** `pkill -f "claude"` matches
the shell running that very command and kills it mid-command — the symptom is a
compound command dying with exit 143/144 and no explanation. Find the PID
(`ps aux | grep "[c]laude"`) and kill that. The same trap applies to any server
started this way.

**"Address already in use" after a restart means the old process is still
alive.** Verify the new process owns the port by checking *its own* log for a
bind error, not by curling the port — a curl 200 may be answered by the stale
process you meant to replace, which silently keeps serving old configuration.

## Things it will not do

- **No agent panel for the user.** Driving over `send-keys` loses arrow-key
  selection, per-teammate transcripts and Esc-to-interrupt. This route suits
  unattended runs, not hands-on use.
- **Teammate models are fixed at spawn.** `/model` affects only the lead, so
  name the model when spawning instead.
- **The container is ephemeral.** Session state and any credential die with it.
  Anything worth keeping must be committed and pushed.

## Related

To expose a port from this container to the outside world alongside the nested
session, use the **nested-cli-ngrok** skill, which adds tunnel setup.
