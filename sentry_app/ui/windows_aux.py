import tkinter as tk
from tkinter import ttk, filedialog, Menu
import datetime
import webbrowser
from ..utils import convert_steamid3_to_steamid64
from .dialogs import custom_popup, custom_askstring

class BaseAuxWindow:
    def __init__(self, root, logic, px_func, title, w, h):
        self.root = root
        self.logic = logic
        self.window = tk.Toplevel(root)
        self.window.title(title)
        self.px = px_func
        self.window.transient(root)
        self.window.grab_set()
        self.window.focus_set()
        self.window.geometry(f"{self.px(w)}x{self.px(h)}")

        self.window.grid_rowconfigure(0, weight=1)
        self.window.grid_columnconfigure(0, weight=1)

        self.container = ttk.Frame(self.window)
        self.container.grid(row=0, column=0, sticky="nsew")
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.window.bind("<Button-1>", self.on_click_anywhere)

    def create_table(self, columns):
        self.tree = ttk.Treeview(self.container, columns=columns, show="headings")
        vsb = ttk.Scrollbar(self.container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

    def on_click_anywhere(self, event):
        if hasattr(self, 'menu'):
            try:
                self.menu.unpost()
            except: pass

        if not isinstance(event.widget, (ttk.Treeview, ttk.Scrollbar)):
            if hasattr(self, 'tree') and self.tree.selection():
                self.tree.selection_remove(self.tree.selection())

class UserListWindow(BaseAuxWindow):
    def __init__(self, root, logic, px_func):
        super().__init__(root, logic, px_func, "User List Manager", 900, 500)

        cols = ("name", "steamid", "type", "date_added", "last_seen", "notes")
        self.create_table(cols)

        self.tree.heading("name", text="Name", anchor="center")
        self.tree.heading("steamid", text="SteamID", anchor="center")
        self.tree.heading("type", text="Type", anchor="center")
        self.tree.heading("date_added", text="Added", anchor="center")
        self.tree.heading("last_seen", text="Seen", anchor="center")
        self.tree.heading("notes", text="Notes", anchor="center")

        self.tree.column("name", width=self.px(150), anchor="center", stretch=True)
        self.tree.column("steamid", width=self.px(130), anchor="center", stretch=False)
        self.tree.column("type", width=self.px(80), anchor="center", stretch=False)
        self.tree.column("date_added", width=self.px(90), anchor="center", stretch=False)
        self.tree.column("last_seen", width=self.px(90), anchor="center", stretch=False)
        self.tree.column("notes", width=self.px(200), anchor="center", stretch=True)

        footer = ttk.Frame(self.window, padding=self.px(10))
        footer.grid(row=1, column=0, sticky="ew")
        ttk.Button(footer, text="Export list to TF2BD format", command=self.export).pack(side="left")
        ttk.Button(footer, text="Close", command=self.window.destroy).pack(side="right")

        self.setup_context_menu()
        self.tree.bind("<Button-3>", self.on_right_click)
        self.refresh()

    def setup_context_menu(self):
        self.menu = Menu(self.window, tearoff=0)
        self.menu.add_command(label="Type: Cheater", command=lambda: self.set_type("Cheater"))
        self.menu.add_command(label="Type: Suspicious", command=lambda: self.set_type("Suspicious"))
        self.menu.add_command(label="Type: Other", command=lambda: self.set_type("Other"))
        self.menu.add_separator()
        self.menu.add_command(label="Edit Notes", command=self.edit_notes)
        self.menu.add_command(label="Delete Entry", command=self.delete_entry)
        self.menu.add_separator()
        self.menu.add_command(label="Copy SteamID", command=self.copy_id)
        self.menu.add_command(label="Open Profile", command=self.open_profile)
        self.menu.add_command(label="Open SteamHistory Profile", command=self.open_steamhistory)

    def on_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.sel_sid = item
            self.menu.post(event.x_root, event.y_root)

    def set_type(self, ptype):
        if self.sel_sid:
            self.logic.mark_player(self.sel_sid, ptype)
            self.refresh()

    def edit_notes(self):
        if self.sel_sid:
            curr = self.logic.lists.get_user_notes(self.sel_sid)
            new_note = custom_askstring(self.window, self.px, "Edit Notes", "Notes:", initialvalue=curr)
            self.window.grab_set()
            self.window.focus_set()
            if new_note is not None:
                ptype = self.logic.lists.identify_player_type(self.sel_sid) or "Other"
                self.logic.mark_player(self.sel_sid, ptype, notes=new_note)
                self.refresh()

    def delete_entry(self):
        if self.sel_sid:
            self.logic.delete_player(self.sel_sid)
            self.refresh()

    def copy_id(self):
        if self.sel_sid:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.sel_sid)
            self.root.update()

    def open_profile(self):
        if self.sel_sid:
            s64 = convert_steamid3_to_steamid64(self.sel_sid)
            webbrowser.open(f"https://steamcommunity.com/profiles/{s64}")

    def open_steamhistory(self):
        if self.sel_sid:
            s64 = convert_steamid3_to_steamid64(self.sel_sid)
            if s64:
                webbrowser.open(f"https://steamhistory.net/id/{s64}")

    def refresh(self):
        for i in self.tree.get_children(): self.tree.delete(i)

        entries = self.logic.lists.user_entries
        entries.sort(key=lambda x: x.get('time_added', 0), reverse=True)

        col_cheat = self.logic.get_setting('Color_Cheater')
        col_sus = self.logic.get_setting('Color_Suspicious')
        col_oth = self.logic.get_setting('Color_Other')
        self.tree.tag_configure('Cheater', background=col_cheat)
        self.tree.tag_configure('Suspicious', background=col_sus)
        self.tree.tag_configure('Other', background=col_oth)

        for e in entries:
            ts_add = e.get('time_added', 0)
            ts_see = e.get('time_last_seen', 0)
            d_add = datetime.datetime.fromtimestamp(ts_add).strftime('%Y-%m-%d') if ts_add else "-"
            d_see = datetime.datetime.fromtimestamp(ts_see).strftime('%Y-%m-%d') if ts_see else "-"

            self.tree.insert("", "end", iid=e['steamid'],
                             values=(e.get('last_seen_name'), e['steamid'], e['player_type'], d_add, d_see, e.get('notes')),
                             tags=(e['player_type'],))

    def export(self):
        fn = filedialog.asksaveasfilename(parent=self.window, defaultextension=".json", filetypes=[("JSON", "*.json")])
        if fn:
            ok, msg = self.logic.lists.export_to_tf2bd(fn)
            self.show_info("Export Result", msg)

class RecentPlayersWindow(BaseAuxWindow):
    def __init__(self, root, logic, px_func):
        super().__init__(root, logic, px_func, "Recent Players", 600, 400)

        cols = ("name", "steamid", "mark", "notes")
        self.create_table(cols)

        self.tree.heading("name", text="Name", anchor="center")
        self.tree.heading("steamid", text="SteamID", anchor="center")
        self.tree.heading("mark", text="Mark", anchor="center")
        self.tree.heading("notes", text="Notes", anchor="center")

        # Explicit widths
        self.tree.column("name", width=self.px(180), anchor="center", stretch=True)
        self.tree.column("steamid", width=self.px(130), anchor="center", stretch=False)
        self.tree.column("mark", width=self.px(80), anchor="center", stretch=False)
        self.tree.column("notes", width=self.px(190), anchor="center", stretch=True)

        footer = ttk.Frame(self.window, padding=self.px(10))
        footer.grid(row=1, column=0, sticky="ew")
        ttk.Button(footer, text="Close", command=self.window.destroy).pack(side="right")

        self.setup_context_menu()
        self.tree.bind("<Button-3>", self.on_right_click)
        self.refresh_loop()

    def setup_context_menu(self):
        self.menu = Menu(self.window, tearoff=0)
        self.menu.add_command(label="Mark Cheater", command=lambda: self.mark("Cheater"))
        self.menu.add_command(label="Mark Suspicious", command=lambda: self.mark("Suspicious"))
        self.menu.add_command(label="Mark Other", command=lambda: self.mark("Other"))
        self.menu.add_separator()
        self.menu.add_command(label="Edit Notes", command=self.edit_notes)
        self.menu.add_command(label="Delete Entry", command=self.delete_entry)
        self.menu.add_separator()
        self.menu.add_command(label="Copy SteamID", command=self.copy_id)
        self.menu.add_command(label="Open Profile", command=self.open_profile)
        self.menu.add_command(label="Open SteamHistory Profile", command=self.open_steamhistory)

    def refresh_loop(self):
        if not self.window.winfo_exists(): return
        self.refresh()
        self.window.after(2000, self.refresh_loop)

    def refresh(self):
        players = self.logic.get_recently_played_snapshot()
        existing = set(self.tree.get_children())

        col_cheat = self.logic.get_setting_color('Color_Cheater')
        col_sus = self.logic.get_setting_color('Color_Suspicious')
        col_other = self.logic.get_setting_color('Color_Other')
        col_self = self.logic.get_setting_color('Color_Self')

        self.tree.tag_configure('Cheater', background=col_cheat, foreground='black')
        self.tree.tag_configure('Suspicious', background=col_sus, foreground='black')
        self.tree.tag_configure('Other', background=col_other, foreground='black')
        self.tree.tag_configure('Self', background=col_self, foreground='black')

        for p in players:
            mark = self.logic.lists.get_mark_label(p.steamid)
            vals = (p.name, p.steamid, mark, p.notes or "")

            raw_type = self.logic.lists.identify_player_type(p.steamid)

            if p.steamid == self.logic.get_current_user_steamid3():
                raw_type = "Self"

            tags = (raw_type,) if raw_type else ()

            if p.steamid in existing:
                self.tree.item(p.steamid, values=vals, tags=tags)
                existing.remove(p.steamid)
            else:
                self.tree.insert("", "end", iid=p.steamid, values=vals, tags=tags)

    def on_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.sel_sid = item
            self.menu.post(event.x_root, event.y_root)

    def mark(self, ptype):
        if self.sel_sid:
            self.logic.mark_recently_played(self.sel_sid, ptype, self.logic.recently_played)
            self.refresh()

    def edit_notes(self):
        if self.sel_sid:
            curr = self.logic.lists.get_user_notes(self.sel_sid)
            new_note = custom_askstring(self.window, self.px, "Edit Notes", "Notes:", initialvalue=curr)
            self.window.grab_set()
            self.window.focus_set()
            if new_note is not None:
                ptype = self.logic.lists.identify_player_type(self.sel_sid) or "Other"
                self.logic.mark_player(self.sel_sid, ptype, notes=new_note)
                self.refresh()

    def delete_entry(self):
        if self.sel_sid:
            self.logic.delete_player(self.sel_sid)
            self.refresh()

    def copy_id(self):
        if self.sel_sid:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.sel_sid)
            self.root.update()

    def open_profile(self):
        if self.sel_sid:
            s64 = convert_steamid3_to_steamid64(self.sel_sid)
            webbrowser.open(f"https://steamcommunity.com/profiles/{s64}")

    def open_steamhistory(self):
        if self.sel_sid:
            s64 = convert_steamid3_to_steamid64(self.sel_sid)
            if s64:
                webbrowser.open(f"https://steamhistory.net/id/{s64}")
