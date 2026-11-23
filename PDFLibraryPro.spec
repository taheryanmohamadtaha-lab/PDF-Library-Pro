# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hidden = collect_submodules("app") + ["PySide6.QtSvg", "PySide6.QtXml"]
excludes = ["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick",
            "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
            "PySide6.QtBluetooth", "PySide6.QtSensors", "tkinter", "matplotlib", "numpy.tests"]

a = Analysis(["run.py"], pathex=["."], datas=[("app/resources", "app/resources")],
             hiddenimports=hidden, excludes=excludes, noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="PDFLibraryPro", debug=False, strip=False, upx=False,
          console=False, icon="app/resources/app.ico")
