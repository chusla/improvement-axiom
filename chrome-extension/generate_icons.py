"""Generate simple PNG icons for the Chrome extension.

Run: python chrome-extension/generate_icons.py

Requires no dependencies beyond the standard library.
Creates minimal valid PNG files using raw bytes.
"""

import struct
import zlib
import os

def create_png(width, height, pixels):
    """Create a minimal PNG file from raw RGBA pixel data."""
    def chunk(chunk_type, data):
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))

    raw_data = b""
    for y in range(height):
        raw_data += b"\x00"  # filter byte
        for x in range(width):
            idx = (y * width + x) * 4
            raw_data += bytes(pixels[idx:idx + 4])

    idat = chunk(b"IDAT", zlib.compress(raw_data))
    iend = chunk(b"IEND", b"")

    return header + ihdr + idat + iend


def draw_icon(size):
    """Draw the Axiom icon: purple gradient rounded rect with a partial ring."""
    pixels = [0] * (size * size * 4)
    cx, cy = size / 2, size / 2
    r_outer = size * 0.38
    r_inner = size * 0.10
    ring_width = max(1.5, size * 0.07)
    corner_r = size * 0.2

    for y in range(size):
        for x in range(size):
            idx = (y * size + x) * 4

            # Rounded rect mask
            dx = max(0, max(corner_r - x, x - (size - 1 - corner_r)))
            dy = max(0, max(corner_r - y, y - (size - 1 - corner_r)))
            if dx * dx + dy * dy > corner_r * corner_r:
                pixels[idx:idx + 4] = [0, 0, 0, 0]
                continue

            # Background gradient (indigo to purple)
            t = (x + y) / (2 * size)
            rr = int(99 + (139 - 99) * t)
            gg = int(102 + (92 - 102) * t)
            bb = int(241 + (246 - 241) * t)

            # Distance from center
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5

            # Ring
            import math
            angle = math.atan2(y - cy, x - cx)
            if angle < 0:
                angle += 2 * math.pi

            on_ring = abs(dist - r_outer) < ring_width and angle < math.pi * 1.7
            on_dot = dist < r_inner

            if on_ring or on_dot:
                # White with slight transparency
                pixels[idx] = 255
                pixels[idx + 1] = 255
                pixels[idx + 2] = 255
                pixels[idx + 3] = 220 if on_ring else 200
            else:
                pixels[idx] = rr
                pixels[idx + 1] = gg
                pixels[idx + 2] = bb
                pixels[idx + 3] = 255

    return pixels


def main():
    icons_dir = os.path.join(os.path.dirname(__file__), "icons")
    os.makedirs(icons_dir, exist_ok=True)

    for size in [16, 48, 128]:
        pixels = draw_icon(size)
        png_data = create_png(size, size, pixels)
        path = os.path.join(icons_dir, f"icon{size}.png")
        with open(path, "wb") as f:
            f.write(png_data)
        print(f"Created {path} ({len(png_data)} bytes)")


if __name__ == "__main__":
    main()
