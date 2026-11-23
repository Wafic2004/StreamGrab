import os
from string import Template

from .utils import data_dir

DARK = dict(
    bg="#0d0f14", surface="#15181f", surface2="#1c2029", border="#262b36", border_strong="#323846",
    text="#e9ebf1", muted="#8b93a7", input="#11141a",
    accent="#7c6cff", accent_hover="#9184ff", accent_press="#6a59f0", accent_text="#ffffff",
    accent_soft="#2e7c6cff", success="#34d399", danger="#ff6b78", warning="#fbbf24",
)
LIGHT = dict(
    bg="#f2f3f7", surface="#ffffff", surface2="#f5f6fa", border="#e1e4eb", border_strong="#cfd4de",
    text="#151821", muted="#667085", input="#ffffff",
    accent="#6553f5", accent_hover="#7666ff", accent_press="#5443e0", accent_text="#ffffff",
    accent_soft="#226553f5", success="#0f9f6e", danger="#e5484d", warning="#b7791f",
)


def palette(dark):
    return DARK if dark else LIGHT


def _assets(p, dark):
    d = os.path.join(data_dir(), "assets")
    os.makedirs(d, exist_ok=True)
    name = "dark" if dark else "light"
    chev = os.path.join(d, f"chevron_{name}.svg")
    with open(chev, "w", encoding="utf-8") as f:
        f.write(
            '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
            f'<path d="M2.5 4.5 L6 8 L9.5 4.5" fill="none" stroke="{p["muted"]}" stroke-width="1.6" '
            'stroke-linecap="round" stroke-linejoin="round"/></svg>'
        )
    chk = os.path.join(d, "check.svg")
    with open(chk, "w", encoding="utf-8") as f:
        f.write(
            '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14">'
            '<path d="M3.2 7.3 L5.8 9.8 L10.8 4.4" fill="none" stroke="#ffffff" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round"/></svg>'
        )
    return chev.replace("\\", "/"), chk.replace("\\", "/")


QSS = Template(r"""
* { color: $text; outline: none; }
QMainWindow, QDialog { background: $bg; }
QWidget#root, QWidget#dialogRoot { background: $bg; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QToolTip { background: $surface2; color: $text; border: 1px solid $border; border-radius: 6px; padding: 6px 8px; }

QFrame#card { background: $surface; border: 1px solid $border; border-radius: 16px; }
QFrame#divider { background: $border; max-height: 1px; min-height: 1px; border: none; }

QLabel { background: transparent; }
QLabel#appName { font-size: 15pt; font-weight: 700; }
QLabel#appTag { color: $muted; font-size: 9pt; }
QLabel#section { color: $muted; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }
QLabel#fieldLabel { color: $muted; font-size: 9pt; font-weight: 600; }
QLabel#videoTitle { font-size: 12.5pt; font-weight: 600; }
QLabel#meta { color: $muted; font-size: 9.5pt; }
QLabel#badge { background: $surface2; border: 1px solid $border; border-radius: 7px; padding: 2px 8px; color: $muted; font-size: 8.5pt; font-weight: 600; }
QLabel#badgeAccent { background: $accent_soft; border: 1px solid $accent_soft; border-radius: 7px; padding: 2px 8px; color: $accent_hover; font-size: 8.5pt; font-weight: 700; }
QLabel#emptyTitle { font-size: 11.5pt; font-weight: 600; }
QLabel#emptyText { color: $muted; }
QLabel#errorText { color: $danger; font-weight: 600; }
QLabel#estimateSize { font-size: 15pt; font-weight: 700; }
QLabel#estimateDesc { color: $muted; font-size: 9.5pt; }
QLabel#hint { color: $warning; font-size: 9pt; }
QLabel#statusHead { font-size: 11pt; font-weight: 600; }
QLabel#statusHead[state="ok"] { color: $success; }
QLabel#statusHead[state="error"] { color: $danger; }
QLabel#statusDetail { color: $muted; font-size: 9.5pt; }
QLabel#pct { font-size: 11pt; font-weight: 700; color: $accent_hover; }

QLineEdit { background: $input; border: 1px solid $border; border-radius: 11px; padding: 10px 14px; font-size: 10.5pt; selection-background-color: $accent; selection-color: #fff; }
QLineEdit:hover { border-color: $border_strong; }
QLineEdit:focus { border: 2px solid $accent; }
QLineEdit:disabled { color: $muted; }

QPushButton { background: $surface2; border: 1px solid $border; border-radius: 11px; padding: 9px 16px; font-weight: 600; }
QPushButton:hover { border-color: $accent; background: $surface2; }
QPushButton:pressed { background: $border; }
QPushButton:disabled { color: $muted; border-color: $border; }
QPushButton#primary { background: $accent; color: $accent_text; border: 1px solid $accent; }
QPushButton#primary:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton#primary:pressed { background: $accent_press; }
QPushButton#primary:disabled { background: $border; border-color: $border; color: $muted; }
QPushButton#big { font-size: 11pt; padding: 12px 26px; border-radius: 12px; }
QPushButton#ghost { background: transparent; border: 1px solid transparent; padding: 7px 10px; border-radius: 9px; }
QPushButton#ghost:hover { background: $surface2; border-color: $border; }
QPushButton#danger { background: transparent; border: 1px solid $border; color: $danger; }
QPushButton#danger:hover { border-color: $danger; }
QPushButton { outline: none; }
QPushButton:focus { border: 2px solid $accent; }
QPushButton#primary:focus { border: 2px solid $text; }
QPushButton#ghost:focus { border: 2px solid $accent; }
QPushButton#danger:focus { border: 2px solid $danger; }

QFrame#segment { background: $input; border: 1px solid $border; border-radius: 13px; }
QPushButton#seg { background: transparent; border: 1px solid transparent; border-radius: 10px; padding: 10px 14px; color: $muted; font-weight: 600; }
QPushButton#seg:hover { color: $text; }
QPushButton#seg:checked { background: $accent; color: $accent_text; border-color: $accent; }
QPushButton#seg:focus { border: 2px solid $accent; color: $text; }
QPushButton#seg:checked:focus { border: 2px solid $text; color: $accent_text; }
QPushButton#seg:disabled { color: $muted; }
QPushButton#seg:checked:disabled { background: $border_strong; color: $text; border-color: $border_strong; }

QComboBox { background: $input; border: 1px solid $border; border-radius: 10px; padding: 8px 12px; min-height: 20px; }
QComboBox:hover { border-color: $border_strong; }
QComboBox:focus, QComboBox:on { border: 2px solid $accent; }
QComboBox:disabled { color: $muted; }
QComboBox::drop-down { border: none; width: 30px; subcontrol-origin: padding; subcontrol-position: center right; }
QComboBox::down-arrow { image: url($chevron); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: $surface; border: 1px solid $border; padding: 4px; outline: 0; }
QComboBox QAbstractItemView::item { padding: 7px 10px; min-height: 22px; border-radius: 6px; }
QComboBox QAbstractItemView::item:hover { background: $surface2; }
QComboBox QAbstractItemView::item:selected { background: $accent; color: $accent_text; }
QComboBox QAbstractItemView::item:disabled { color: $muted; }

QProgressBar { background: $input; border: 1px solid $border; border-radius: 5px; max-height: 10px; min-height: 10px; text-align: center; color: transparent; }
QProgressBar::chunk { border-radius: 4px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent, stop:1 $accent_hover); }
QProgressBar#thin { max-height: 4px; min-height: 4px; border: none; border-radius: 2px; }
QProgressBar#thin::chunk { border-radius: 2px; }

QCheckBox { spacing: 9px; background: transparent; outline: none; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 6px; border: 1px solid $border_strong; background: $input; }
QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator:focus { border: 2px solid $accent; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url($check); }
QCheckBox:disabled { color: $muted; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 4px 2px; }
QScrollBar::handle:vertical { background: $border_strong; border-radius: 3px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $muted; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QMessageBox { background: $surface; }
""")


def build_stylesheet(p, dark):
    chev, chk = _assets(p, dark)
    return QSS.substitute(**p, chevron=chev, check=chk)
