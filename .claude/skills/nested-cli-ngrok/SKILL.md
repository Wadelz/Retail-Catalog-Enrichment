---
name: nested-cli-ngrok
description: Open a nested interactive Claude Code CLI in tmux and expose a local port to the internet through an ngrok tunnel — installs the ngrok binary, configures the authtoken, connects, and reports the public URL. Use when work in this container has to be reachable from outside it: a dashboard the user opens in their browser, a webhook that must call back in, a collector or service on another machine, or when the user says "tunnel this out", "install ngrok", "expose port N", or "I can't reach it from my laptop".
---

# Nested CLI plus an ngrok tunnel

## Why this exists

Two separate walls, and this skill gets through both.

**The TTY wall.** Claude Code gates some features on an interactive session,
meaning the process's I/O mode. A web or SDK session has no TTY, so it fails the
check. A second `claude` in a tmux pty does not. That half is the
**nested-cli** skill, and this skill uses its script directly.

**The network wall.** This container has no public inbound address. Anything
listening here is invisible to the user's browser and to any service that needs
to call in. A tunnel gives a local port a public HTTPS URL.

## The combined flow

```bash
NESTED=../nested-cli/scripts/nested.sh          # from this skill's directory
NGROK=scripts/ngrok-tunnel.sh

bash "$NESTED" start --permission-mode acceptEdits
bash "$NGROK" install
export NGROK_AUTHTOKEN=...                       # set out of band, see below
bash "$NGROK" auth
bash "$NGROK" start 6006                         # prints the public URL
```

| Command | What it does |
| --- | --- |
| `install` | Download and install the ngrok binary |
| `auth` | Configure the authtoken from `$NGROK_AUTHTOKEN` |
| `start <port>` | Open a tunnel and print the public URL |
| `url` | Print the current public URL(s) |
| `status` | Binary / auth / tunnel state |
| `stop` | Terminate the tunnel |

For everything about driving the nested session itself — first-run prompts,
blocked panes, placeholder text, killing by PID — read the **nested-cli** skill.
It is not repeated here.

## The authtoken

ngrok needs a free account token from
<https://dashboard.ngrok.com/get-started/your-authtoken>.

`auth` reads it from `$NGROK_AUTHTOKEN` and **never** takes it as an argument,
because a positional secret lands in shell history and in `ps` output for every
process on the box. Ask the user to export it, or set it in the environment
configuration, rather than pasting it into the conversation: unlike a
short-lived OAuth code, an authtoken is long-lived and reusable, so a
conversation transcript keeps working as a credential until it is rotated.

## Before exposing anything

**A tunnel URL is public to anyone who has it.** There is no authentication in
front of it unless the service behind it provides one. Whatever you expose is
world-reachable for as long as the tunnel is up, so turn on that service's own
auth first — and say so plainly rather than assuming the user has thought about
it. An observability collector, for instance, carries full prompts and model
outputs.

**Free-tier URLs are ephemeral.** They change on every agent restart, so
anything configured to point at one needs rewiring after a restart. If a
consumer suddenly starts failing, check whether the tunnel was recycled before
debugging anything else.

**The tunnel dies with the process.** Nothing here survives the container being
reclaimed.

## Egress policy can block tunnels outright — check before promising one

The container's egress proxy enforces an organization policy, and **tunnel hosts
can be denied by it**. This is not hypothetical: a working
`trycloudflare.com` tunnel in one session was later refused with
`connect_rejected (the egress proxy denied the CONNECT)` after a restart, with
no change on the tunnel's side.

So verify reachability before telling the user a tunnel will work:

```bash
curl -sS "$HTTPS_PROXY/__agentproxy/status"   # recentRelayFailures names blocked hosts
```

A `connect_rejected` for the tunnel host means the policy blocks it, not that
the tunnel is broken. Retrying, reinstalling, or switching tunnel providers will
not fix a policy denial — say so, and fall back to running the service on the
user's own machine instead.

Note the direction that still works: this container can *reach out* to a service
the user exposes from their laptop. When outbound is permitted but inbound is
blocked, put the tunnel on their side, not this one.

## Verifying it actually works

`start` polls ngrok's local API on `:4040` and returns the public URL only once
the agent reports a live tunnel, so a URL from it has already been confirmed.
Then check the tunnel end to end rather than trusting that:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<public-url>/
```

- **200** — working.
- **502** — the tunnel is up but nothing is listening on the local port. Start
  the service; this is not a tunnel fault.
- **connect_rejected / 000** — egress policy, per above.

`ngrok` is not a TTY program, so redirecting its output is safe. Do not
generalise that to the nested `claude` process, whose stdout must never be
redirected — see nested-cli.
