"""Light/dark palettes + accent colour -> Qt style sheet."""
from dataclasses import dataclass

ACCENTS = {"purple": "#8b5cf6", "orange": "#f59e0b", "blue": "#3b82f6", "green": "#10b981", "red": "#ef4444",
           "pink": "#ec4899"}


def rgba(hex_color: str, alpha: float) -> str:
    """Qt style sheets read #RRGGBBAA as #AARRGGBB, so always emit rgba()."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{int(alpha * 255)})"


@dataclass
class Palette:
    bg: str
    panel: str
    card: str
    border: str
    text: str
    muted: str
    accent: str
    dark: bool

    @property
    def hover(self):
        return "rgba(255,255,255,20)" if self.dark else "rgba(0,0,0,16)"


def palette(dark: bool, accent: str) -> Palette:
    acc = ACCENTS.get(accent, accent if accent.startswith("#") else ACCENTS["purple"])
    if dark:
        return Palette("#18181b", "#202024", "#2a2a30", "#34343c", "#ececf1", "#9a9aa6", acc, True)
    return Palette("#f4f4f7", "#ffffff", "#ffffff", "#dcdce4", "#1f1f27", "#6b6b78", acc, False)


def stylesheet(p: Palette, font: str) -> str:
    return f"""
* {{ font-family: '{font}', 'Segoe UI', Tahoma, sans-serif; font-size: 13px; }}
QWidget {{ background: {p.bg}; color: {p.text}; }}
QFrame#sidebar {{ background: {p.panel}; border: none; }}
QFrame#topbar {{ background: {p.bg}; }}
QFrame#card, QFrame#statcard {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 12px; }}
QFrame#card QLabel, QFrame#statcard QLabel {{ background: transparent; }}
QLabel#h1 {{ font-size: 22px; font-weight: bold; background: transparent; }}
QLabel#h2 {{ font-size: 15px; font-weight: bold; background: transparent; }}
QLabel#muted {{ color: {p.muted}; background: transparent; }}
QLabel {{ background: transparent; }}
QPushButton {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 8px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: {p.accent}; }}
QPushButton#primary {{ background: {p.accent}; color: white; border: none; font-weight: bold; }}
QPushButton#primary:hover {{ background: {rgba(p.accent, .8)}; }}
QPushButton#danger {{ color: #ef4444; }}
QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 6px; }}
QToolButton:hover {{ background: {p.hover}; }}
QToolButton:checked {{ background: {rgba(p.accent, .2)}; }}
QToolButton#nav {{ padding: 9px 10px; text-align: start; }}
QToolButton#nav:checked {{ background: {rgba(p.accent, .18)}; color: {p.accent}; font-weight: bold; }}
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox, QTextBrowser {{ background: {p.card};
  border: 1px solid {p.border}; border-radius: 8px; padding: 5px 8px; selection-background-color: {p.accent}; }}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{ border-color: {p.accent}; }}
QComboBox QAbstractItemView {{ background: {p.card}; selection-background-color: {p.accent}; }}
QListWidget, QTreeWidget, QListView, QTableWidget {{ background: {p.panel}; border: 1px solid {p.border};
  border-radius: 10px; outline: 0; }}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}
QListWidget::item:selected, QTreeWidget::item:selected {{ background: {rgba(p.accent, .33)}; color: {p.text}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 5px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QProgressBar {{ background: {p.border}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 4px; }}
QMenu {{ background: {p.card}; border: 1px solid {p.border}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p.accent}; color: white; }}
QToolTip {{ background: {p.card}; color: {p.text}; border: 1px solid {p.border}; }}
QTabBar::tab {{ background: transparent; padding: 7px 12px; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ border-bottom: 2px solid {p.accent}; color: {p.accent}; }}
QTabWidget::pane {{ border: none; }}
QSplitter::handle {{ background: {p.border}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {p.border}; background: {p.card}; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}
QStatusBar {{ background: {p.panel}; }}
"""
