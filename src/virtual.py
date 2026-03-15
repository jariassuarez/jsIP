import os
import struct
import fcntl
import time

from .mappings import DS4_BUTTON_CODES, DS4_AXIS_CODES

# Event types
EV_KEY = 0x01
EV_ABS = 0x03
EV_SYN = 0x00
SYN_REPORT = 0

# uinput_user_dev struct: name(80s) + id(4H) + ff_effects_max(I) + absmax(64i) + absmin(64i) + absfuzz(64i) + absflat(64i)
UINPUT_USER_DEV_FORMAT = '80sHHHHI' + 'i' * 64 * 4

# input_event struct: timeval(ll) + type(H) + code(H) + value(i)
INPUT_EVENT_FORMAT = 'llHHi'

# ioctl codes: _IOW('U', nr, int) = (1<<30)|(4<<16)|(0x55<<8)|nr
UI_SET_EVBIT  = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_ABSBIT = 0x40045567
UI_DEV_CREATE  = 0x5501
UI_DEV_DESTROY = 0x5502


class VirtualDS4:
    def __init__(self, device='/dev/uinput', name='Virtual DS4'):
        self.device = device
        self.name = name
        self.fd = None

    def _ioctl(self, request, arg=0):
        fcntl.ioctl(self.fd, request, arg)

    def _setup(self):
        self.fd = os.open(self.device, os.O_WRONLY | os.O_NONBLOCK)

        # Enable EV_KEY and EV_ABS
        self._ioctl(UI_SET_EVBIT, EV_KEY)  # UI_SET_EVBIT EV_KEY
        self._ioctl(UI_SET_EVBIT, EV_ABS)  # UI_SET_EVBIT EV_ABS

        # Register buttons
        for code in DS4_BUTTON_CODES.values():
            self._ioctl(UI_SET_KEYBIT, code)  # UI_SET_KEYBIT

        # Register axes
        for code in DS4_AXIS_CODES.values():
            self._ioctl(UI_SET_ABSBIT, code)  # UI_SET_ABSBIT

        # Build uinput_user_dev
        absmax  = [32767] * 64
        absmin  = [-32767] * 64
        absfuzz = [16]    * 64
        absflat = [128]   * 64

        # D-pad is -1/0/1
        for code in [0x10, 0x11]:
            absmax[code]  =  1
            absmin[code]  = -1
            absfuzz[code] =  0
            absflat[code] =  0

        dev = struct.pack(
            UINPUT_USER_DEV_FORMAT,
            self.name.encode()[:79],
            0x03, 0x054C, 0x05C4, 0x0100,  # BUS_USB, Sony vendor, DS4 product, version
            0,                              # ff_effects_max
            *absmax, *absmin, *absfuzz, *absflat
        )
        os.write(self.fd, dev)
        fcntl.ioctl(self.fd, 0x5501, b'\x00')  # UI_DEV_CREATE

        time.sleep(0.1)  # give kernel time to register the device

    def _emit(self, type_, code, value):
        t = time.time()
        sec  = int(t)
        usec = int((t - sec) * 1_000_000)
        event = struct.pack(INPUT_EVENT_FORMAT, sec, usec, type_, code, value)
        os.write(self.fd, event)

    def _sync(self):
        self._emit(EV_SYN, SYN_REPORT, 0)

    def send_button(self, name, pressed):
        code = DS4_BUTTON_CODES.get(name)
        if code is None:
            print(f"[warn] unknown button: {name!r}")
            return
        self._emit(EV_KEY, code, int(pressed))
        self._sync()

    def send_axis(self, name, value):
        """value should be in [-32767, 32767]"""
        code = DS4_AXIS_CODES.get(name)
        if code is None:
            print(f"[warn] unknown axis: {name!r}")
            return
        self._emit(EV_ABS, code, value)
        self._sync()

    def close(self):
        if self.fd is None:
            return
        try:
            fcntl.ioctl(self.fd, 0x5502, b'\x00')  # UI_DEV_DESTROY
        except OSError as e:
            print(f"[warn] UI_DEV_DESTROY failed: {e}")
        finally:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        self._setup()
        return self

    def __exit__(self, *args):
        self.close()