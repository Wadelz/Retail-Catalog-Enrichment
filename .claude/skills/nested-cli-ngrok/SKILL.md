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

## Which direction the tunnel must run — measured, not assumed

**A tunnel agent cannot run from this container if it needs a port other than
443.** Outbound egress here is a 443 proxy, and tunnel agents do not all use
443:

| Agent | Control port | Works from this container |
| --- | --- | --- |
| ngrok (`connect.ngrok-agent.com`) | 443 | reachable |
| cloudflared (`*.v2.argotunnel.com`) | **7844** | **blocked** |

That is why this skill is built on ngrok rather than cloudflared, despite
cloudflared quick tunnels needing no account. A `cloudflared tunnel --url` run
here fails its own precheck:

```
ERROR: Allow outbound TCP on port 7844.
UDP Connectivity  ... QUIC connection failed     status=fail
TCP Connectivity  ... blocked or unreachable     status=fail
```

The public hostname is still issued, so it *looks* like it worked — every
request then returns **HTTP 530**, because the edge has no registered
connection behind it.

**Check the agent's control port, not the hostname.** Probing
`argotunnel.com:443` succeeds and proves nothing, because the tunnel protocol
does not run on 443. Probe the port the agent actually dials:

```bash
timeout 10 bash -c 'exec 3<>/dev/tcp/region1.v2.argotunnel.com/7844' \
  && echo reachable || echo blocked
```

**Prefer the other direction whenever it is available.** Outbound from this
container is permitted, so a service the user exposes from their own machine is
reachable from here — with cloudflared on *their* laptop, where 7844 is open and
a quick tunnel needs no account at all. Running the tunnel on their side is
usually less work than running it on this one.

## Reading a failed tunnel URL

Three failures look alike from the outside and mean different things:

- **HTTP 530** — the agent never registered a connection. Read the agent's own
  log; this is the port-blocked case above, not a fault in the exposed service.
- **HTTP 502** — the tunnel is up but nothing is listening on the local port.
  Start the service.
- **`connect_rejected` / HTTP 000** — the CONNECT failed. The proxy reports this
  as "denied by policy **or could not reach the destination**", and the second
  half is much the more common cause: a tunnel whose agent has stopped leaves a
  dead hostname that fails exactly this way. Do not report a policy block on
  this evidence alone — confirm the agent is still running first.

## Verifying it actually works

`start` polls ngrok's local API on `:4040` and returns the public URL only once
the agent reports a live tunnel, so a URL from it has already been confirmed.
Then check the tunnel end to end rather than trusting that:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<public-url>/
```

A 200 means working; anything else is covered by **Reading a failed tunnel URL**
above.

`ngrok` is not a TTY program, so redirecting its output is safe. Do not
generalise that to the nested `claude` process, whose stdout must never be
redirected — see nested-cli.
