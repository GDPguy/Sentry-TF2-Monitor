import tkinter.font as tkfont
from tkinter import ttk

def apply_ui_scaling(root, user_scale=1.0):
    dpi = root.winfo_fpixels('1i')
    auto = dpi / 72.0
    root.tk.call('tk', 'scaling', auto)

    default_font = tkfont.nametofont("TkDefaultFont")
    text_font    = tkfont.nametofont("TkTextFont")
    fixed_font   = tkfont.nametofont("TkFixedFont")

    new_size = max(9, int(10 * float(user_scale)))

    default_font.configure(size=new_size)
    text_font.configure(size=new_size)
    fixed_font.configure(size=new_size)

    root.option_add("*Menu*Font", default_font)

def apply_ttk_scaling(root, user_scale=1.0):
    style = ttk.Style(root)
    base_font = tkfont.nametofont("TkDefaultFont")

    style.configure(".", font=base_font)
    style.configure("TLabel", font=base_font)
    style.configure("TButton", font=base_font)
    style.configure("TEntry", font=base_font)
    style.configure("TCheckbutton", font=base_font)
    style.configure("TRadiobutton", font=base_font)
    style.configure("Treeview", font=base_font)
    style.configure("Treeview.Heading", font=base_font)
    style.configure("TLabelframe.Label", font=base_font)

    style.configure("Treeview", rowheight=max(24, int(24 * float(user_scale))))
