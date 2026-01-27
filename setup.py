import sys
from cx_Freeze import setup, Executable

build_exe_options = {
    "packages": ["os", "sys", "psutil", "valve", "requests", "PySide6"],
    "includes": [
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets"
    ],
    "excludes": ["tkinter"],
    "include_files": [],
}

base = "gui" if sys.platform == "win32" else None

setup(
    name="Sentry",
    version="1.0.0",
    description="Sentry Application",
    options={"build_exe": build_exe_options},
    executables=[Executable("run.py", base=base, target_name="Sentry.exe")]
)
