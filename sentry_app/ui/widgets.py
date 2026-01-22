import tkinter as tk
from tkinter import ttk

class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, *, scroll_x=False, scroll_y=True, fit_width=True, **kwargs):
        super().__init__(parent, **kwargs)

        self.scroll_x = scroll_x
        self.scroll_y = scroll_y
        self.fit_width = fit_width

        self.canvas = tk.Canvas(self, highlightthickness=0, confine=True)
        self.content = ttk.Frame(self.canvas)
        self._mw_bind_after = None

        # Theme matching
        style = ttk.Style()
        try:
            bg_color = style.lookup("TFrame", "background")
            self.canvas.configure(bg=bg_color)
        except Exception:
            pass

        self.vsb = None
        self.hsb = None

        if self.scroll_y:
            self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
            self.canvas.configure(yscrollcommand=self.vsb.set)

        if self.scroll_x:
            self.hsb = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
            self.canvas.configure(xscrollcommand=self.hsb.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        if self.vsb:
            self.vsb.grid(row=0, column=1, sticky="ns")
        if self.hsb:
            self.hsb.grid(row=1, column=0, sticky="ew")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")

        self._sr_after = None
        self._w_after = None

        self.content.bind("<Configure>", self._schedule_scrollregion)

        if self.fit_width and not self.scroll_x:
            self.canvas.bind("<Configure>", self._schedule_fit_width)

        self._wheel_bindings = []
        self._wheel_toplevel = None
        self._bind_mousewheel_safely()
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _bind_mousewheel_safely(self):
        if self._wheel_bindings:
            return

        if not self.winfo_exists():
            return

        try:
            tl = self.winfo_toplevel()
            self._wheel_toplevel = tl

            def safe_bind(sequence, func):
                funcid = tl.bind(sequence, func, add="+")
                self._wheel_bindings.append((sequence, funcid))

            safe_bind("<MouseWheel>", self._on_mousewheel_anywhere)
            safe_bind("<Shift-MouseWheel>", self._on_shift_mousewheel_anywhere)
            safe_bind("<Button-4>", self._on_mousewheel_linux_anywhere)
            safe_bind("<Button-5>", self._on_mousewheel_linux_anywhere)
            safe_bind("<Shift-Button-4>", self._on_shift_mousewheel_linux_anywhere)
            safe_bind("<Shift-Button-5>", self._on_shift_mousewheel_linux_anywhere)

            return  # success, stop here

        except Exception:
            pass

        if self._mw_bind_after is None:
            self._mw_bind_after = self.after(50, self._mw_bind_retry)

    def _mw_bind_retry(self):
        self._mw_bind_after = None
        self._bind_mousewheel_safely()

    def _on_destroy(self, event):
        if event.widget is not self:
            return

        if self._wheel_toplevel and self._wheel_bindings:
            try:
                for sequence, funcid in self._wheel_bindings:
                    try:
                        self._wheel_toplevel.unbind(sequence, funcid)
                    except tk.TclError:
                        pass
            except Exception:
                pass
            self._wheel_bindings.clear()

    def _is_pointer_inside_me(self, x_root, y_root):
        w = self.winfo_containing(x_root, y_root)
        while w is not None:
            if w == self:
                return True
            w = getattr(w, "master", None)
        return False

    def _is_nested_scrollable(self, x_root, y_root):
        target = self.winfo_containing(x_root, y_root)
        while target and target != self:
            if isinstance(target, (ttk.Treeview, tk.Text, tk.Listbox, ttk.Scrollbar, tk.Scrollbar)):
                return True
            target = getattr(target, "master", None)
        return False

    def _can_scroll_y(self):
        first, last = self.canvas.yview()
        return not (first <= 0.0 and last >= 1.0)

    def _can_scroll_x(self):
        first, last = self.canvas.xview()
        return not (first <= 0.0 and last >= 1.0)

    def _schedule_scrollregion(self, event=None):
        if self._sr_after is not None:
            self.after_cancel(self._sr_after)
        self._sr_after = self.after(30, self._update_scrollregion)

    def _update_scrollregion(self):
        self._sr_after = None
        self.update_idletasks()
        bbox = self.canvas.bbox(self.window_id)
        if not bbox: return
        x0, y0, x1, y1 = bbox
        content_w = max(0, x1 - x0)
        content_h = max(0, y1 - y0)
        view_w = self.canvas.winfo_width()
        view_h = self.canvas.winfo_height()
        sr_w = max(content_w, view_w)
        sr_h = max(content_h, view_h)
        self.canvas.configure(scrollregion=(0, 0, sr_w, sr_h))
        if content_h <= view_h + 1:
            self.canvas.yview_moveto(0)
        if content_w <= view_w + 1:
            self.canvas.xview_moveto(0)

    def _schedule_fit_width(self, event=None):
        if self._w_after is not None:
            self.after_cancel(self._w_after)
        self._w_after = self.after(30, self._fit_width)

    def _fit_width(self):
        self._w_after = None
        w = self.canvas.winfo_width()
        if w > 1:
            self.canvas.itemconfigure(self.window_id, width=w)

    # ---- Handlers ----

    def _on_mousewheel_anywhere(self, event):
        if not self.scroll_y: return
        if not self._is_pointer_inside_me(event.x_root, event.y_root): return
        if self._is_nested_scrollable(event.x_root, event.y_root): return
        if not self._can_scroll_y(): return

        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    def _on_shift_mousewheel_anywhere(self, event):
        if not self.scroll_x: return
        if not self._is_pointer_inside_me(event.x_root, event.y_root): return
        if self._is_nested_scrollable(event.x_root, event.y_root): return
        if not self._can_scroll_x(): return

        self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    def _on_mousewheel_linux_anywhere(self, event):
        if not self.scroll_y: return
        if not self._is_pointer_inside_me(event.x_root, event.y_root): return
        if self._is_nested_scrollable(event.x_root, event.y_root): return
        if not self._can_scroll_y(): return

        self.canvas.yview_scroll(-1 if event.num == 4 else 1, "units")
        return "break"

    def _on_shift_mousewheel_linux_anywhere(self, event):
        if not self.scroll_x: return
        if not self._is_pointer_inside_me(event.x_root, event.y_root): return
        if self._is_nested_scrollable(event.x_root, event.y_root): return
        if not self._can_scroll_x(): return

        self.canvas.xview_scroll(-1 if event.num == 4 else 1, "units")
        return "break"
