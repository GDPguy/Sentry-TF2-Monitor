import tkinter as tk
from tkinter import ttk, Menu, messagebox, simpledialog
import threading
import queue
import webbrowser
import datetime
import copy

from .widgets import ScrollableFrame
from .windows_settings import SettingsWindow
from .windows_aux import UserListWindow, RecentPlayersWindow
from .dialogs import custom_popup, custom_askstring
from ..consts import APP_VERSION
from ..utils import convert_steamid3_to_steamid64

class MainWindow:
    def __init__(self, root, app_logic):
        self.root = root
        self.logic = app_logic
        self.root.title(f"Sentry v{APP_VERSION} - TF2 Server Monitor")

        self.px_scale = (self.root.winfo_fpixels("1i") / 96.0) * self.logic.get_setting_float("UI_Scale")

        self.data_queue = queue.Queue()
        self.is_fetching = False

        self.selected_steamid = None
        self.selected_name = None

        self.setup_ui()

        self.root.after(100, self.process_queue_loop)
        self.root.after(2000, self.tick_update_data)
        self.logic.start_automation_thread()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def px(self, v):
        return max(1, int(v * self.px_scale))

    def on_close(self):
        try:
            self.logic.stop_automation_thread()
        except Exception:
            pass
        self.root.destroy()

    def setup_ui(self):
        w, h = self.px(800), self.px(950)
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(self.px(600), self.px(400))

        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self.main_scroll = ScrollableFrame(self.root, scroll_x=False, scroll_y=True, fit_width=True)
        self.main_scroll.grid(row=0, column=0, sticky="nsew")
        self.content = self.main_scroll.content

        top = ttk.Frame(self.content, padding=5)
        top.pack(fill="x")

        ttk.Button(top, text="Settings", command=self.open_settings).pack(side="left", padx=5)
        ttk.Button(top, text="Recent Players", command=self.open_recent).pack(side="left", padx=5)
        ttk.Button(top, text="User List", command=self.open_userlist).pack(side="left", padx=5)

        self.lbl_status = ttk.Label(top, text="Initializing...", foreground="cyan", anchor="center")
        self.lbl_status.pack(side="left", fill="x", expand=True, padx=10)

        self.red_table = self.create_team_table("RED", 12)
        self.blue_table = self.create_team_table("BLU", 12)
        self.spec_table = self.create_team_table("Spectator / Unassigned", 4)

        self.setup_context_menu()
        self.root.bind("<Button-1>", self.on_global_click, add="+")

        if self.logic.lists.userlist_error:
            self.root.after(500, lambda: custom_popup(self.root, self.px, "Userlist Error", self.logic.lists.userlist_error))
        if self.logic.lists.tf2bd_error:
            self.root.after(1000, lambda: custom_popup(self.root, self.px, "TF2BD Error", self.logic.lists.tf2bd_error))

    def create_team_table(self, title, height):
        frame = ttk.LabelFrame(self.content, text=title, padding=(5,5))
        frame.pack(padx=10, pady=5, fill="both", expand=True)

        cols = ('name', 'ping', 'kills', 'deaths', 'steamid', 'bans', 'mark', 'notes')
        tree = ttk.Treeview(frame, columns=cols, show='headings', height=height)

        tree.heading('name', text='Name', anchor='center')
        tree.column('name', width=self.px(150), anchor='center', stretch=False)

        headers = [('ping',40), ('kills',40), ('deaths',50), ('steamid',130), ('bans',60), ('mark',70)]
        for c, w in headers:
            text = "SteamID" if c == 'steamid' else c.title()
            tree.heading(c, text=text, anchor='center')
            tree.column(c, width=self.px(w), anchor='center', stretch=False)

        tree.heading('notes', text='Notes', anchor='center')
        tree.column(
            'notes',
            width=self.px(150),
            minwidth=self.px(80),
            anchor='center',
            stretch=True,
        )

        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)

        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        col_self = self.logic.get_setting_color('Color_Self')
        col_cheat = self.logic.get_setting_color('Color_Cheater')
        col_sus = self.logic.get_setting_color('Color_Suspicious')
        col_other = self.logic.get_setting_color('Color_Other')

        tree.tag_configure('Self', background=col_self, foreground='black')
        tree.tag_configure('Cheater', background=col_cheat, foreground='black')
        tree.tag_configure('Suspicious', background=col_sus, foreground='black')
        tree.tag_configure('Other', background=col_other, foreground='black')

        return tree

    def tick_update_data(self):
        if not self.is_fetching:
            self.is_fetching = True
            threading.Thread(target=self._data_worker, daemon=True).start()
        self.root.after(2000, self.tick_update_data)

    def _data_worker(self):
        try:
            res = self.logic.get_players()
            res = copy.deepcopy(res)
        except Exception as e:
            print(f"Error in data worker: {e}")
            res = ('connection_failed', [], [], [])
        self.data_queue.put(res)

    def process_queue_loop(self):
        got_any = False
        try:
            while True:
                res = self.data_queue.get_nowait()
                got_any = True
                self.handle_data_result(res)
        except queue.Empty:
            pass
        finally:
            if got_any:
                self.is_fetching = False
            self.root.after(100, self.process_queue_loop)

    def handle_data_result(self, result):
        status = result[0]

        steamid_status_msg = ""
        using_override = self.logic.get_setting_bool('Use_Manual_SteamID')
        effective_id = self.logic.get_current_user_steamid3()
        is_effective_valid = effective_id and "XXXXXXXXXX" not in effective_id

        if not is_effective_valid:
            if using_override:
                steamid_status_msg = "\nOverride enabled: Enter SteamID3 in Settings"
            else:
                steamid_status_msg = "\nSteamID not detected (Is Steam running?).\nTry providing a fallback SteamID3 in settings."
        if status == 'tf2_closed':
            self.lbl_status.config(text="Waiting for TF2 to launch", foreground="cyan")
            self.clear_tables()
        elif status == 'lobby_not_found':
            self.lbl_status.config(text=f"RCON connected.{steamid_status_msg}", foreground="green")
            self.clear_tables()
        elif status == 'connection_failed':
            msg = (
                "TF2 is running, but RCon is unreachable. If this persists,\n"
                "ensure your TF2 launch options include:\n"
                "+ip 0.0.0.0 +rcon_password yourpass +net_start -usercon -g15\n"
                "and check settings." + steamid_status_msg
            )
            self.lbl_status.config(text=msg, foreground="orange")
        elif status == 'banned':
            self.lbl_status.config(text="RCON Banned (Restart TF2)", foreground="red")
            self.clear_tables()
        elif status == 'auth_failed':
            self.lbl_status.config(text="RCON Error: Wrong Password.\nCheck TF2's launch options & Settings > RCon Password", foreground="orange")
            self.clear_tables()

        else:
            _, red, blue, spec = result
            self.update_tree(self.red_table, red)
            self.update_tree(self.blue_table, blue)
            self.update_tree(self.spec_table, spec)

            total = len(red) + len(blue) + len(spec)

            player_word = "player" if total == 1 else "players"
            if steamid_status_msg:
                self.lbl_status.config(
                    text=f"Connected. Monitoring {total} {player_word}. {steamid_status_msg}",
                    foreground="orange"
                )
            else:
                self.lbl_status.config(
                    text=f"Connected. Monitoring {total} {player_word}.",
                    foreground="green"
                )

    def update_tree(self, tree, players):
        existing_ids = set(tree.get_children())
        seen_ids = set()

        my_sid = self.logic.get_current_user_steamid3()

        for p in players:
            row_id = str(p.userid)
            seen_ids.add(row_id)

            tag = ""
            if p.steamid == my_sid: tag = "Self"
            elif p.player_type in ("Cheater", "Suspicious", "Other"): tag = p.player_type

            bans = self.logic.get_sourcebans_count(p.steamid)
            mark = self.logic.lists.get_mark_label(p.steamid)

            vals = (p.name, p.ping, p.kills, p.deaths, p.steamid, bans, mark, p.notes)

            if row_id in existing_ids:
                tree.item(row_id, values=vals, tags=(tag,))
            else:
                tree.insert("", "end", iid=row_id, values=vals, tags=(tag,))

        for iid in existing_ids:
            if iid not in seen_ids:
                tree.delete(iid)

    def clear_tables(self):
        for t in [self.red_table, self.blue_table, self.spec_table]:
            t.delete(*t.get_children())

    def setup_context_menu(self):
        self.menu = Menu(self.root, tearoff=0)
        self.menu.add_command(label="Mark Cheater", command=lambda: self.action_mark("Cheater"))
        self.menu.add_command(label="Mark Suspicious", command=lambda: self.action_mark("Suspicious"))
        self.menu.add_command(label="Mark Other", command=lambda: self.action_mark("Other"))
        self.menu.add_command(label="Delete User Entry", command=self.action_delete)
        self.menu.add_separator()
        self.menu.add_command(label="Edit Notes", command=self.action_edit_notes)
        self.menu.add_command(label="View SourceBans", command=self.action_view_sb)
        self.menu.add_command(label="View TF2BD Info", command=self.action_view_tf2bd)
        self.menu.add_command(label="Open Profile", command=self.action_profile)
        self.menu.add_command(label="Open SteamHistory Profile", command=self.action_view_sh)
        self.menu.add_separator()
        self.menu.add_command(label="Votekick player", command=self.action_kick)
        self.menu.add_command(label="Copy SteamID", command=self.action_copy)

        for t in [self.red_table, self.blue_table, self.spec_table]:
            t.bind("<Button-3>", lambda e, tbl=t: self.on_right_click(e, tbl))

    def on_right_click(self, event, table):
        item = table.identify_row(event.y)
        if item:
            table.selection_set(item)
            vals = table.item(item, "values")
            self.selected_steamid = vals[4]
            self.selected_name = vals[0]
            self.menu.post(event.x_root, event.y_root)

    def on_global_click(self, event):
        try:
            if event.widget.winfo_class() == 'Menu': return
        except: pass

        self.menu.unpost()
        if not isinstance(event.widget, (ttk.Treeview, ttk.Scrollbar)):
            for t in [self.red_table, self.blue_table, self.spec_table]:
                if t.selection(): t.selection_remove(t.selection())

    def action_mark(self, ptype):
        if self.selected_steamid:
            self.logic.mark_player(self.selected_steamid, ptype, name=self.selected_name)

    def action_edit_notes(self):
        if not self.selected_steamid: return
        curr = self.logic.lists.get_user_notes(self.selected_steamid)
        new_note = custom_askstring(self.root, self.px, "Edit Notes", "Enter notes:", initialvalue=curr)
        if new_note is not None:
            ptype = self.logic.lists.identify_player_type(self.selected_steamid) or "Other"
            self.logic.mark_player(self.selected_steamid, ptype, notes=new_note, name=self.selected_name)

    def action_kick(self):
        if self.selected_steamid:
            self.logic.kick_player(self.selected_steamid)

    def action_delete(self):
        if self.selected_steamid:
            if custom_popup(self.root, self.px, "Confirm", f"Delete entry for {self.selected_steamid}?", is_confirmation=True):
                self.logic.delete_player(self.selected_steamid)

    def action_profile(self):
        if self.selected_steamid:
            s64 = convert_steamid3_to_steamid64(self.selected_steamid)
            if s64: webbrowser.open(f"https://steamcommunity.com/profiles/{s64}")

    def action_view_sh(self):
        if self.selected_steamid:
            s64 = convert_steamid3_to_steamid64(self.selected_steamid)
            if s64:
                webbrowser.open(f"https://steamhistory.net/id/{s64}")

    def action_view_sb(self):
        if self.selected_steamid:
            data = self.logic.get_sourcebans_details(self.selected_steamid)
            if not data:
                custom_popup(self.root, self.px, "SourceBans", "No recent SourceBan data found for this player.")
                return
            lines = []
            for b in data:
                bd = datetime.datetime.fromtimestamp(b.get('BanTimestamp', 0)).strftime('%Y-%m-%d')
                lines.append(f"Date: {bd}\nServer: {b.get('Server')}\nReason: {b.get('BanReason')}\nState: {b.get('CurrentState')}\n")
            self.show_text_viewer(f"SourceBans - {self.selected_steamid}", "\n".join(lines))

    def action_view_tf2bd(self):
        if self.selected_steamid:
            notes = self.logic.lists.get_tf2bd_notes(self.selected_steamid)
            self.show_text_viewer(f"TF2BD Info - {self.selected_steamid}", notes)

    def action_copy(self):
        if self.selected_steamid:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.selected_steamid)
            self.root.update()

    def open_settings(self): SettingsWindow(self.root, self.logic, px_func=self.px)
    def open_userlist(self): UserListWindow(self.root, self.logic, px_func=self.px)
    def open_recent(self): RecentPlayersWindow(self.root, self.logic, px_func=self.px)

    def show_text_viewer(self, title, text):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        w, h = self.px(700), self.px(450)
        win.geometry(f"{w}x{h}")

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)

        txt = tk.Text(frame, wrap="word", highlightthickness=0, borderwidth=0, relief="flat")
        sb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)

        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        txt.insert("1.0", text)
        txt.configure(state="disabled")

        style = ttk.Style()
        try:
            bg = style.lookup("TFrame", "background")
            fg = "white"
            txt.configure(bg=bg, fg=fg)
        except: pass

        footer = ttk.Frame(win, padding=10)
        footer.pack(fill="x", side="bottom")
        ttk.Button(footer, text="Close", command=win.destroy).pack(side="right")
