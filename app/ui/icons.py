"""Stroke icon set (24x24) rendered from inline SVG so no binary assets are needed."""
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

P = {
 "home": '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
 "library": '<path d="M3 21h18"/><path d="M5 21V10M9 21V10M15 21V10M19 21V10"/><path d="M2 10l10-7 10 7z"/>',
 "books": '<rect x="3" y="4" width="4" height="16" rx="1"/><rect x="9" y="4" width="4" height="16" rx="1"/><path d="M15.5 5.5l3.8-1 3 14.5-3.8 1z"/>',
 "shelf": '<path d="M3 4h18M3 12h18M3 20h18"/><path d="M6 4v8M10 6v6M14 12v8M18 14v6"/>',
 "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 "bookopen": '<path d="M2 5c4-1 7 0 10 2 3-2 6-3 10-2v14c-4-1-7 0-10 2-3-2-6-3-10-2z"/><path d="M12 7v14"/>',
 "heart": '<path d="M12 21s-8-5-8-11a4.5 4.5 0 018-3 4.5 4.5 0 018 3c0 6-8 11-8 11z"/>',
 "folder": '<path d="M3 6h6l2 2h10v11H3z"/>',
 "tag": '<path d="M3 12V3h9l9 9-9 9z"/><circle cx="7.5" cy="7.5" r="1"/>',
 "users": '<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-4 3-6 6-6s6 2 6 6"/><path d="M16 5a3 3 0 010 6M18 14c2 1 3 3 3 6"/>',
 "note": '<path d="M5 3h10l4 4v14H5z"/><path d="M15 3v4h4M8 12h8M8 16h8"/>',
 "sparkles": '<path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z"/><path d="M19 3v4M17 5h4"/>',
 "backup": '<path d="M12 3v12M7 10l5 5 5-5M4 20h16"/>',
 "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/>',
 "plus": '<path d="M12 5v14M5 12h14"/>',
 "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
 "grid": '<rect x="4" y="4" width="7" height="7"/><rect x="13" y="4" width="7" height="7"/><rect x="4" y="13" width="7" height="7"/><rect x="13" y="13" width="7" height="7"/>',
 "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
 "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
 "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
 "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
 "bookmark": '<path d="M6 3h12v18l-6-4-6 4z"/>',
 "highlight": '<path d="M4 20h7M14 4l6 6-8 8H8v-4z"/>',
 "zoomin": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4M8 11h6M11 8v6"/>',
 "zoomout": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4M8 11h6"/>',
 "rotate": '<path d="M20 12a8 8 0 10-3 6.2"/><path d="M20 5v7h-7"/>',
 "fullscreen": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
 "left": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
 "right": '<path d="M5 12h14M13 6l6 6-6 6"/>',
 "up": '<path d="M12 19V5M6 11l6-6 6 6"/>',
 "down": '<path d="M12 5v14M6 13l6 6 6-6"/>',
 "fitw": '<path d="M3 12h18M7 8l-4 4 4 4M17 8l4 4-4 4"/>',
 "fitp": '<rect x="6" y="3" width="12" height="18" rx="1"/>',
 "cols": '<rect x="3" y="4" width="8" height="16" rx="1"/><rect x="13" y="4" width="8" height="16" rx="1"/>',
 "file": '<path d="M6 3h8l5 5v13H6z"/><path d="M14 3v5h5"/>',
 "check": '<path d="M5 12l5 5 9-10"/>',
 "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/>',
 "x": '<path d="M6 6l12 12M18 6L6 18"/>',
 "star": '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
 "quote": '<path d="M5 17c0-5 1-8 5-10M13 17c0-5 1-8 5-10"/>',
 "chev": '<path d="M9 6l6 6-6 6"/>',
}


def pixmap(name: str, color: str = "#ffffff", size: int = 22, stroke: float = 1.8) -> QPixmap:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{P.get(name, P["file"])}</svg>')
    r = QSvgRenderer(QByteArray(svg.encode()))
    ratio = 2
    img = QImage(size * ratio, size * ratio, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    r.render(p)
    p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str = "#ffffff", size: int = 22) -> QIcon:
    return QIcon(pixmap(name, color, size))
