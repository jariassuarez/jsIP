import argparse
import socket
import sys

from .server import list_joysticks, JoystickSender, CONTROL_PORT
from .receiver import JoystickReceiver

DEFAULT_EVENT_PORT = 5005


def cmd_list():
    joysticks = list_joysticks()
    if not joysticks:
        print("No joystick devices found under /dev/input/js*")
        return
    print("Available joystick devices:")
    for i, (path, name) in enumerate(joysticks):
        print(f"  [{i}] {path}  ({name})")


def cmd_server(args):
    joysticks = list_joysticks()
    if not joysticks:
        print("No joystick devices found under /dev/input/js*")
        sys.exit(1)

    if args.all:
        selected = list(range(len(joysticks)))
    elif args.devices:
        selected = args.devices
    else:
        print("Available joystick devices:")
        for i, (path, name) in enumerate(joysticks):
            print(f"  [{i}] {path}  ({name})")
        raw = input("Select devices to send (e.g. '0 1', or 'all'): ").strip()
        if raw.lower() == 'all':
            selected = list(range(len(joysticks)))
        else:
            selected = [int(x) for x in raw.split()]

    if not selected:
        print("No devices selected.")
        sys.exit(1)

    event_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ctrl_sock.bind((args.host, args.port))
    print(f"Waiting for client on control port {args.port}...")
    _, receiver_addr = ctrl_sock.recvfrom(1)
    ctrl_sock.close()
    print(f"[info] client connected from {receiver_addr}")

    senders = []
    for device_id, idx in enumerate(selected):
        path, name = joysticks[idx]
        senders.append(JoystickSender(path, device_id, name, event_sock, receiver_addr))

    for s in senders:
        s.send_handshake()
        print(f"[handshake] device_id={s.device_id} -> {s.device} ({s.name})")

    for s in senders:
        s.start()

    try:
        input("Sending... press Enter to stop.\n")
    finally:
        for s in senders:
            s.stop()
        event_sock.close()


def cmd_client(args):
    with JoystickReceiver(args.bind, args.port, args.host) as receiver:
        try:
            input("Listening... press Enter to stop.\n")
        except KeyboardInterrupt:
            pass


def main():
    parser = argparse.ArgumentParser(
        prog='jsip',
        description='Stream joystick events over UDP and replay them as virtual devices.',
    )
    parser.add_argument('--list', action='store_true', help='List local joystick devices and exit')

    subparsers = parser.add_subparsers(dest='command')

    # server
    sp = subparsers.add_parser('server', help='Read local joysticks and stream events to a client')
    sp.add_argument('--host', default='', metavar='ADDR',
                    help='Interface to bind (default: all interfaces)')
    sp.add_argument('--port', type=int, default=CONTROL_PORT, metavar='PORT',
                    help=f'Control port to listen on (default: {CONTROL_PORT})')
    sp.add_argument('--devices', nargs='+', type=int, metavar='ID',
                    help='Device indices to stream (see jsip --list)')
    sp.add_argument('--all', action='store_true',
                    help='Stream all detected joystick devices')

    # client
    cp = subparsers.add_parser('client', help='Receive events from a server and create virtual devices')
    cp.add_argument('--host', required=True, metavar='ADDR',
                    help='Server host to connect to')
    cp.add_argument('--port', type=int, default=DEFAULT_EVENT_PORT, metavar='PORT',
                    help=f'Local port to receive events on (default: {DEFAULT_EVENT_PORT})')
    cp.add_argument('--bind', default='0.0.0.0', metavar='ADDR',
                    help='Local interface to bind (default: 0.0.0.0)')

    args = parser.parse_args()

    if args.list:
        cmd_list()
        return

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == 'server':
        cmd_server(args)
    elif args.command == 'client':
        cmd_client(args)


if __name__ == '__main__':
    main()
