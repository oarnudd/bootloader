import sys
import serial
import struct
import zlib
import time
import subprocess
import enum

# Configuration
PORT = "/dev/ttyACM0"
BAUDRATE = 115200
debug_print = False
chunk_size = 256
kill_screen = True

FIRMWARE_FILE = sys.argv[1] + ".bin"  # Firmware file


class State(enum.Enum):
    HANDSHAKE = 1
    SIZE = 2
    FILE = 3
    CRC = 4
    FINISHED = 5


def kill_screen_on_uart(port):
    try:
        subprocess.run(["pkill", "-f", f"SCREEN {port}"], check=True)
        print(f"Killed screen session on {port}")
    except subprocess.CalledProcessError:
        print(f"No screen session found on {port}")


def read_message(ser, size, blocking=False):
    try:
        if blocking:
            ser.timeout = None
        else:
            ser.timeout = 0.2
        if size == 0:
            response = ser.readline()
        else:
            response = ser.readline(size)
        if response:
            decoded = response.decode(errors="ignore").strip()
            if debug_print:
                print(f"{decoded}")
            return decoded
    except serial.Timeout:
        ser.timeout = 0.2
        return None
    ser.timeout = 0.2
    return None


def send_firmware():

    try:
        with open(FIRMWARE_FILE, "rb") as f:
            firmware_data = f.read()
    except FileNotFoundError:
        print("Error: Firmware file not found!")
        sys.exit(1)

    if kill_screen:
        kill_screen_on_uart(PORT)

    print(f"Firmware file: {FIRMWARE_FILE}")
    print(f"Firmware size: {len(firmware_data)} bytes\n")
    print("Restart device to initiate update")
    print("Waiting for handshake..")

    state = State.HANDSHAKE

    with serial.Serial(PORT, BAUDRATE) as ser:
        ser.timeout = 0.1

        firmware_size_bytes = struct.pack(">I", len(firmware_data))
        ser.write(bytearray(firmware_size_bytes))

        crc = zlib.crc32(firmware_data) & 0xFFFFFFFF
        crc_bytes = struct.pack(">I", crc)

        while True:
            time.sleep(0.1)
            match state:
                case State.HANDSHAKE:
                    ser.write(b"U")
                    time.sleep(0.1)
                    msg = read_message(ser, 3)
                    if msg and "ACK" in msg:
                        ser.write(b"A")
                        time.sleep(0.1)
                        msg = read_message(ser, 3)
                        if msg and "ACK" in msg:
                            print("Handshake completed, updating..")
                            state = State.SIZE

                case State.SIZE:
                    ser.write(bytearray(firmware_size_bytes))
                    msg = read_message(ser, len(str(len(firmware_data))))
                    if msg and str(len(firmware_data)) in msg:
                        state = State.FILE
                    else:
                        time.sleep(1.0)

                case State.FILE:
                    for i in range(0, len(firmware_data), chunk_size):
                        chunk = firmware_data[i: i + chunk_size]
                        ser.write(bytearray(chunk))
                        print(f"Sent {i + len(chunk)
                                      } / {len(firmware_data)
                                           } bytes", end="\r")
                    msg = read_message(ser, 3)
                    if msg and "ACK" in msg:
                        print()
                        print("Binary transfer completed!")
                        state = State.CRC

                case State.CRC:
                    ser.write(bytearray(crc_bytes))
                    msg = read_message(ser, len(bytearray(crc)))
                    if msg and str(crc) in msg:
                        print("CRC transfer completed!")
                        state = State.FINISHED

                case State.FINISHED:
                    msg = read_message(ser, 0)
                    if msg:
                        if "ACK" in msg:
                            break
                        print(msg)


if __name__ == "__main__":
    send_firmware()
