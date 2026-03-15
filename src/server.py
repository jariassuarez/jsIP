'''
struct js_event {
        __u32 time;     /* event timestamp in milliseconds */
        __s16 value;    /* value */
        __u8 type;      /* event type */
        __u8 number;    /* axis/button number */
};

js file has this format according to https://www.kernel.org/doc/html/latest/input/joydev/joystick-api.html
uint32, int16, uint8, uint8 = 8 bytes

#define JS_EVENT_BUTTON         0x01    /* button pressed/released */
#define JS_EVENT_AXIS           0x02    /* joystick moved */
#define JS_EVENT_INIT           0x80    /* initial state of device */

'''

import glob
import struct
import threading
import socket

JS_EVENT_FORMAT = '=IhBB'
JS_EVENT_SIZE = struct.calcsize(JS_EVENT_FORMAT)

PKT_HANDSHAKE = 0x00
PKT_EVENT     = 0x01
PKT_REQUEST   = 0x02

# pkt_type(B) + device_id(B) + name(64s)
HANDSHAKE_FORMAT = '=BB64s'
HANDSHAKE_SIZE   = struct.calcsize(HANDSHAKE_FORMAT)

# pkt_type(B) + device_id(B) + seq(H) + time(I) + value(h) + type(B) + number(B)
EVENT_FORMAT = '=BBHIhBB'
EVENT_SIZE   = struct.calcsize(EVENT_FORMAT)

CONTROL_PORT = 5006


def list_joysticks():
    """Return list of (js_path, name) for all available joystick devices."""
    devices = []
    for path in sorted(glob.glob('/dev/input/js*')):
        js_num = path.replace('/dev/input/js', '')
        name_path = f'/sys/class/input/js{js_num}/device/name'
        try:
            with open(name_path) as f:
                name = f.read().strip()
        except OSError:
            name = 'Unknown'
        devices.append((path, name))
    return devices


class JoystickSender:
    def __init__(self, device, device_id, name, sock, addr):
        self.device    = device
        self.device_id = device_id
        self.name      = name
        self.sock      = sock
        self.addr      = addr
        self.stop_event = threading.Event()
        self.thread     = threading.Thread(target=self._run, daemon=True)
        self._seq = 0

    def send_handshake(self):
        name_bytes = self.name.encode()[:63]
        packet = struct.pack(HANDSHAKE_FORMAT, PKT_HANDSHAKE, self.device_id, name_bytes)
        self.sock.sendto(packet, self.addr)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join()

    def _next_seq(self):
        seq = self._seq
        self._seq = (self._seq + 1) % 65536
        return seq

    def _run(self):
        try:
            with open(self.device, 'rb') as js:
                while not self.stop_event.is_set():
                    data = js.read(JS_EVENT_SIZE)
                    if len(data) < JS_EVENT_SIZE:
                        break
                    time, value, type_, number = struct.unpack(JS_EVENT_FORMAT, data)
                    packet = struct.pack(
                        EVENT_FORMAT,
                        PKT_EVENT, self.device_id, self._next_seq(), time, value, type_, number
                    )
                    self.sock.sendto(packet, self.addr)
        except OSError as e:
            print(f"[error] device {self.device}: {e}")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


if __name__ == '__main__':
    joysticks = list_joysticks()
    if not joysticks:
        print("No joystick devices found under /dev/input/js*")
        raise SystemExit(1)

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
        raise SystemExit(1)

    event_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Wait for receiver to request the device list
    ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ctrl_sock.bind(('', CONTROL_PORT))
    print(f"Waiting for receiver on control port {CONTROL_PORT}...")
    _, receiver_addr = ctrl_sock.recvfrom(1)
    ctrl_sock.close()
    print(f"[info] receiver connected from {receiver_addr}")

    # Build senders targeting the receiver's address
    senders = []
    for device_id, idx in enumerate(selected):
        path, name = joysticks[idx]
        senders.append(JoystickSender(path, device_id, name, event_sock, receiver_addr))

    # Send handshakes so receiver can create virtual devices before events arrive
    for s in senders:
        s.send_handshake()
        print(f"[handshake] device_id={s.device_id} → {s.device} ({s.name})")

    for s in senders:
        s.start()

    input("Sending... press Enter to stop.\n")

    for s in senders:
        s.stop()
    event_sock.close()
