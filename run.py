"""PyInstaller / dev launcher (keeps `app` a proper package so relative imports work)."""
import sys

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
