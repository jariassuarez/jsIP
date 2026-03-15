# JsIP: Joystick over IP

Stream physical joystick events over UDP from one machine to another, where they are replayed as virtual DS4 devices via Linux `uinput`.

## Requirements

- Linux with `/dev/uinput` access (client) and `/dev/input/js*` devices (server)
- Python 3.10+
- No external dependencies

## Installation

```bash
pip install .
```

Or for development:

```bash
pip install -e .
```

## Usage

### List local joystick devices

```bash
jsip --list
```

### Server (the machine with the physical joystick)

```bash
# Interactive device selection
jsip server

# Stream specific devices (by index from --list)
jsip server --devices 0 1

# Stream all detected devices
jsip server --all

# Bind to a specific interface / port
jsip server --host 192.168.1.10 --port 5006
```

### Client (the machine that will receive the events)

```bash
# Connect to a server at 192.168.1.10
jsip client --host 192.168.1.10

# Custom local port and bind address
jsip client --host 192.168.1.10 --port 5005 --bind 0.0.0.0
```

## How it works

1. The **client** binds a UDP socket and sends a `PKT_REQUEST` to the server's control port.
2. The **server** receives the request, learns the client's address, and starts streaming joystick events as UDP packets.
3. For each device, a handshake packet is sent first so the client can create the virtual device before events arrive.
4. The **client** uses Linux `uinput` to create virtual DS4 controllers and forwards all incoming events to them.

## Default ports

| Port | Purpose |
|------|---------|
| 5006 | Server control port (server listens, client initiates) |
| 5005 | Client event port (client binds, server sends to) |
