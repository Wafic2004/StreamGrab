"""Generates assets/streamgrab.ico (multi-size, PNG-compressed) from the logo drawn in code."""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa
from PySide6.QtGui import QGuiApplication  # noqa
from streamgrab.icons import draw_logo  # noqa

app = QGuiApplication(sys.argv)
sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
blobs = []
for s in sizes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    draw_logo(s).save(buf, "PNG")
    blobs.append(bytes(ba))

out = os.path.join(ROOT, "assets", "streamgrab.ico")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "wb") as f:
    f.write(struct.pack("<HHH", 0, 1, len(sizes)))
    offset = 6 + 16 * len(sizes)
    for s, b in zip(sizes, blobs):
        d = 0 if s >= 256 else s
        f.write(struct.pack("<BBBBHHII", d, d, 0, 0, 1, 32, len(b), offset))
        offset += len(b)
    for b in blobs:
        f.write(b)
print("wrote", out)
