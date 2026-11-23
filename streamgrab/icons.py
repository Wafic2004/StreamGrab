"""App icon (drawn in code) and Windows Fluent glyph icons."""
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (QIcon, QPixmap, QPainter, QColor, QLinearGradient, QPen, QPainterPath,
                           QFont, QFontDatabase, QGuiApplication)

# Segoe Fluent Icons (Win 11) / Segoe MDL2 Assets (Win 10) code points
G_DOWNLOAD = ""
G_SEARCH = ""
G_PASTE = ""
G_FOLDER = ""
G_OPEN = chr(0xE8A7)
G_BROWSE = chr(0xE8DA)
G_SETTINGS = ""
G_SUN = ""
G_MOON = ""
G_CANCEL = ""
G_PLAY = ""
G_VIDEO = ""
G_MUTE = ""
G_AUDIO = ""
G_LINK = ""
G_CHECK = ""
G_ERROR = ""
G_REFRESH = ""
G_LIST = ""

_glyph_family = None


def glyph_family():
    global _glyph_family
    if _glyph_family is None:
        fams = set(QFontDatabase.families())
        _glyph_family = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in fams), "")
    return _glyph_family


def _dpr():
    app = QGuiApplication.instance()
    s = app.primaryScreen() if app else None
    return max(1.0, s.devicePixelRatio() if s else 1.0)


def glyph_pixmap(glyph, color, size=16):
    dpr = _dpr()
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.setDevicePixelRatio(dpr)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    f = QFont(glyph_family())
    f.setPixelSize(int(size * 0.9))
    p.setFont(f)
    p.setPen(QColor(color))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, glyph)
    p.end()
    return px


def glyph_icon(glyph, color, size=16, on_color=None, disabled_color=None):
    if not glyph_family():
        return QIcon()
    icon = QIcon()
    icon.addPixmap(glyph_pixmap(glyph, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(glyph_pixmap(glyph, on_color or color, size), QIcon.Mode.Normal, QIcon.State.On)
    if disabled_color:
        icon.addPixmap(glyph_pixmap(glyph, disabled_color, size), QIcon.Mode.Disabled, QIcon.State.Off)
    return icon


def draw_logo(size):
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = QRectF(0, 0, size, size).adjusted(size * 0.04, size * 0.04, -size * 0.04, -size * 0.04)
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0, QColor("#9b8cff"))
    g.setColorAt(1, QColor("#5b45f0"))
    path = QPainterPath()
    path.addRoundedRect(r, size * 0.24, size * 0.24)
    p.fillPath(path, g)
    # play triangle + download arrow
    pen = QPen(QColor("white"))
    pen.setWidthF(max(1.5, size * 0.085))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    cx = size / 2
    top, mid, bot = size * 0.26, size * 0.58, size * 0.74
    p.drawLine(QPointF(cx, top), QPointF(cx, mid))
    p.drawLine(QPointF(cx - size * 0.15, mid - size * 0.14), QPointF(cx, mid))
    p.drawLine(QPointF(cx + size * 0.15, mid - size * 0.14), QPointF(cx, mid))
    p.drawLine(QPointF(size * 0.30, bot), QPointF(size * 0.70, bot))
    p.end()
    return px


def app_icon():
    icon = QIcon()
    for s in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(draw_logo(s))
    return icon
