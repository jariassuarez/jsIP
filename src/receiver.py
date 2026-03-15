import struct
import threading
import socket

from mappings import DS4_BUTTONS, DS4_AXES, DS4_BUTTON_CODES, DS4_AXIS_CODES
from virtual import VirtualDS4
from server import (
    PKT_HANDSHAKE, PKT_EVENT, PKT_REQUEST,
    HANDSHAKE_FORMAT, HANDSHAKE_SIZE,
    EVENT_FORMAT, EVENT_SIZE,
    CONTROL_PORT,
)

JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS   = 0x02
JS_EVENT_INIT   = 0x80

MAX_PACKET_SIZE = max(HANDSHAKE_SIZE, EVENT_SIZE)


class JoystickReceiver:
    def __init__(self, host, port, server_host):
        self.addr = (host, port)
        self.server_ctrl_addr = (server_host, CONTROL_PORT)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self._devices: dict[int, VirtualDS4] = {}
        self._lock = threading.Lock()

    def start(self):
        self.sock.bind(self.addr)
        # Initiate handshake: ask server for its device list
        self.sock.sendto(bytes([PKT_REQUEST]), self.server_ctrl_addr)
        print(f"[info] sent PKT_REQUEST to {self.server_ctrl_addr}")
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.sock.close()
        self.thread.join()
        with self._lock:
            for virt in self._devices.values():
                virt.close()
            self._devices.clear()

    def _get_or_create(self, device_id, name=None):
        with self._lock:
            if device_id not in self._devices:
                label = name or f'Virtual DS4 #{device_id}'
                virt = VirtualDS4(name=label)
                virt._setup()
                self._devices[device_id] = virt
                print(f"[info] created virtual device: device_id={device_id} ({label})")
            return self._devices[device_id]

    def _on_handshake(self, device_id, name):
        print(f"[handshake] device_id={device_id} name={name!r}")
        self._get_or_create(device_id, name)

    def _on_event(self, device_id, value, type_, number):
        virt = self._get_or_create(device_id)

        type_ &= ~JS_EVENT_INIT

        if type_ == JS_EVENT_BUTTON:
            self._on_button(virt, number, pressed=bool(value))
        elif type_ == JS_EVENT_AXIS:
            self._on_axis(virt, number, value)

    def _on_button(self, virt, number, pressed):
        name = DS4_BUTTONS.get(number)
        if name and name in DS4_BUTTON_CODES:
            virt.send_button(name, pressed)
        else:
            print(f"[warn] unmapped button number: {number}")

    def _on_axis(self, virt, number, raw):
        name = DS4_AXES.get(number)
        if name and name in DS4_AXIS_CODES:
            virt.send_axis(name, raw)
        else:
            print(f"[warn] unmapped axis number: {number}")

    def _run(self):
        while not self.stop_event.is_set():
            try:
                data, _ = self.sock.recvfrom(MAX_PACKET_SIZE)
                if not data:
                    continue

                pkt_type = data[0]

                if pkt_type == PKT_HANDSHAKE and len(data) >= HANDSHAKE_SIZE:
                    _, device_id, name_bytes = struct.unpack(HANDSHAKE_FORMAT, data[:HANDSHAKE_SIZE])
                    name = name_bytes.rstrip(b'\x00').decode(errors='replace')
                    self._on_handshake(device_id, name)

                elif pkt_type == PKT_EVENT and len(data) >= EVENT_SIZE:
                    _, device_id, _, _, value, type_, number = struct.unpack(EVENT_FORMAT, data[:EVENT_SIZE])
                    self._on_event(device_id, value, type_, number)

            except OSError:
                break  # socket was closed

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


if __name__ == '__main__':
    with JoystickReceiver('0.0.0.0', 5005, server_host='127.0.0.1') as receiver:
        input("Listening... press Enter to stop.\n")
