import struct
import zlib
from pathlib import Path

BAR = (23, 32, 42)
MARK = (255, 255, 255)


def chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def plate_png(size):
    rows = []
    top, bottom = int(size * 0.42), int(size * 0.58)
    left, right = int(size * 0.22), int(size * 0.78)
    for y in range(size):
        row = bytearray()
        band = top <= y < bottom
        for x in range(size):
            row.extend(MARK if band and left <= x < right else BAR)
        rows.append(b"\x00" + bytes(row))
    raw = b"".join(rows)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main():
    folder = Path(__file__).resolve().parent / "static"
    folder.mkdir(exist_ok=True)
    for size in (192, 512):
        (folder / f"icon-{size}.png").write_bytes(plate_png(size))


if __name__ == "__main__":
    main()
