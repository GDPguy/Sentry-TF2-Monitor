# --- START OF FILE sentry_app/ui/dialogs.py ---

import tkinter as tk
from tkinter import ttk

def custom_popup(parent, px_func, title, message, is_confirmation=False):
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.resizable(False, False)
    dialog.withdraw()

    container = ttk.Frame(dialog, padding=px_func(20))
    container.pack(fill="both", expand=True)

    lbl = ttk.Label(container, text=message, wraplength=px_func(350), justify="left")
    lbl.pack(fill="x", pady=(0, px_func(20)))

    btn_frame = ttk.Frame(container)
    btn_frame.pack(fill="x")
    result = [False]

    def on_yes(): result[0] = True; dialog.destroy()
    def on_no(): result[0] = False; dialog.destroy()

    if is_confirmation:
        ttk.Button(btn_frame, text="No", command=on_no, width=8).pack(side="right", padx=(5,0))
        ttk.Button(btn_frame, text="Yes", command=on_yes, width=8).pack(side="right")
    else:
        ttk.Button(btn_frame, text="OK", command=on_yes, width=8).pack(side="right")

    dialog.protocol("WM_DELETE_WINDOW", on_no)
    dialog.update_idletasks()

    x = parent.winfo_x() + (parent.winfo_width()//2) - (dialog.winfo_reqwidth()//2)
    y = parent.winfo_y() + (parent.winfo_height()//2) - (dialog.winfo_reqheight()//2)
    dialog.geometry(f"+{x}+{y}")

    dialog.deiconify()
    dialog.grab_set()
    dialog.wait_window()
    return result[0]

def custom_askstring(parent, px_func, title, prompt, initialvalue=""):
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.resizable(False, False)
    dialog.withdraw()

    container = ttk.Frame(dialog, padding=px_func(10))
    container.pack(fill="both", expand=True)

    ttk.Label(container, text=prompt).pack(anchor="w", pady=(0, 5))
    var = tk.StringVar(value=initialvalue)
    entry = ttk.Entry(container, textvariable=var)
    entry.pack(fill="x", pady=(0, 15))
    entry.focus_set()
    entry.select_range(0, "end")

    result = [None]
    def on_ok(e=None): result[0] = var.get(); dialog.destroy()
    def on_cancel(e=None): dialog.destroy()

    btn_frame = ttk.Frame(container)
    btn_frame.pack(fill="x")
    ttk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side="right", padx=(5,0))
    ttk.Button(btn_frame, text="OK", command=on_ok).pack(side="right")

    dialog.bind("<Return>", on_ok)
    dialog.bind("<Escape>", on_cancel)
    dialog.update_idletasks()

    x = parent.winfo_x() + (parent.winfo_width()//2) - (dialog.winfo_reqwidth()//2)
    y = parent.winfo_y() + (parent.winfo_height()//2) - (dialog.winfo_reqheight()//2)

    dialog.geometry(f"{px_func(300)}x{dialog.winfo_reqheight()}+{x}+{y}")
    dialog.deiconify()
    dialog.grab_set()
    dialog.wait_window()
    return result[0]
