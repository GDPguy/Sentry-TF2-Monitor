import tkinter as tk
import sv_ttk
from sentry_app.logic import AppLogic
from sentry_app.ui.main_window import MainWindow

from sentry_app.ui.style import apply_ui_scaling, apply_ttk_scaling

def main():
    app_logic = AppLogic()
    root = tk.Tk()
    sv_ttk.set_theme("dark")

    scale = app_logic.get_setting_float("UI_Scale")
    if scale <= 0: scale = 1.0

    apply_ui_scaling(root, user_scale=scale)

    apply_ttk_scaling(root, user_scale=scale)

    app = MainWindow(root, app_logic)
    root.mainloop()

if __name__ == "__main__":
    main()
