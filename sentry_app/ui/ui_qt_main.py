import sys
import queue
import threading
import copy
import datetime
import webbrowser

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QLabel, QTableWidget,
                               QTableWidgetItem, QHeaderView, QMenu, QGroupBox,
                               QTextEdit, QDialog, QAbstractItemView, QSizePolicy, QFrame)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QCursor, QFont

from .ui_qt_settings import SettingsWindow
from .ui_qt_aux_windows import UserListWindow, RecentPlayersWindow
from .ui_qt_dialogs import custom_popup
from .ui_qt_shared import SentryTable, ActionHandler, DeselectableWindowMixin, NumericTableWidgetItem
from ..consts import APP_VERSION

class MainWindow(DeselectableWindowMixin, QMainWindow):
    def __init__(self, app_logic):
        super().__init__()
        self.logic = app_logic
        self.actions = ActionHandler(self, app_logic)
        self.setWindowTitle(f"Sentry v{APP_VERSION} - TF2 Server Monitor")

        self.user_scale = self.logic.get_setting_float("UI_Scale")
        if self.user_scale <= 0: self.user_scale = 1.0

        self.data_queue = queue.Queue()
        self.is_fetching = False
        self.is_closing = False

        self.selected_steamid = None
        self.selected_name = None

        self.setup_ui()

        self.queue_timer = QTimer(self)
        self.queue_timer.timeout.connect(self.process_queue)
        self.queue_timer.start(100)

        self.fetch_timer = QTimer(self)
        self.fetch_timer.timeout.connect(self.tick_update_data)
        self.fetch_timer.start(2000)

        self.logic.start_automation_thread()

    def closeEvent(self, event):
        self.is_closing = True
        if self.fetch_timer.isActive(): self.fetch_timer.stop()
        if self.queue_timer.isActive(): self.queue_timer.stop()
        try:
            self.logic.stop_automation_thread()
        except: pass
        event.accept()

    def px(self, v):
        return int(v * self.user_scale)

    def setup_ui(self):
        w, h = self.px(800), self.px(950)
        self.resize(w, h)
        self.setMinimumSize(self.px(600), self.px(400))

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 0, 5, 0)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(5, 5, 5, 0)

        btn_settings = QPushButton("Settings")
        btn_settings.clicked.connect(self.open_settings)
        btn_recent = QPushButton("Recent Players")
        btn_recent.clicked.connect(self.open_recent)
        btn_users = QPushButton("User List")
        btn_users.clicked.connect(self.open_userlist)

        top_bar.addWidget(btn_settings)
        top_bar.addWidget(btn_recent)
        top_bar.addWidget(btn_users)

        self.lbl_status = QLabel("Initializing...")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("color: #008B8B; font-weight: bold;")
        self.lbl_status.setFixedHeight(self.px(30))
        f = self.lbl_status.font()
        f.setPointSizeF(f.pointSizeF() * 0.9)
        self.lbl_status.setFont(f)

        top_bar.addWidget(self.lbl_status, stretch=1)
        main_layout.addLayout(top_bar)

        self.red_table = self.create_team_table("RED")
        self.blue_table = self.create_team_table("BLU")
        self.spec_table = self.create_team_table("Spectator / Unassigned")

        main_layout.addWidget(self.red_table['container'], stretch=3)
        main_layout.addWidget(self.blue_table['container'], stretch=3)
        main_layout.addWidget(self.spec_table['container'], stretch=1)

        self.setup_exclusive_selection()

        if self.logic.lists.userlist_error:
            QTimer.singleShot(500, lambda: custom_popup(self, None, "Userlist Error", self.logic.lists.userlist_error))
        if self.logic.lists.tf2bd_error:
            QTimer.singleShot(1000, lambda: custom_popup(self, None, "TF2BD Error", self.logic.lists.tf2bd_error))

    def create_team_table(self, title):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-weight: bold; padding-left: 2px;")
        layout.addWidget(lbl_title)

        table = SentryTable()
        cols = ['Name', 'Ping', 'Kills', 'Deaths', 'SteamID', 'Bans', 'Mark', 'Notes']
        table.setColumnCount(len(cols))
        table.setHorizontalHeaderLabels(cols)

        table.setSortingEnabled(True)

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)

        widths = [150, 45, 45, 60, 130, 60, 70, 0]
        for i, w in enumerate(widths):
            if w > 0: table.setColumnWidth(i, self.px(w))

        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda p, t=table: self.on_context_menu(p, t))

        table.cellDoubleClicked.connect(lambda r, c, t=table: self.on_double_click(r, c, t))

        layout.addWidget(table)

        return {'container': container, 'table': table}

    def setup_exclusive_selection(self):
        tables = [self.red_table['table'], self.blue_table['table'], self.spec_table['table']]
        def handle_selection(sender):
            if sender.selectedItems():
                for t in tables:
                    if t != sender:
                        t.blockSignals(True)
                        t.clearSelection()
                        t.clearFocus()
                        t.blockSignals(False)
        for t in tables:
            t.itemSelectionChanged.connect(lambda t=t: handle_selection(t))

    def on_double_click(self, row, col, table):
        if col == 7:
            sid_item = table.item(row, 4)
            name_item = table.item(row, 0)
            if sid_item:
                self.selected_steamid = sid_item.text()
                self.selected_name = name_item.text() if name_item else ""
                self.on_edit_notes()

    def on_context_menu(self, pos, table):
        item = table.itemAt(pos)
        if not item: return

        row = item.row()
        table.selectRow(row)

        sid_item = table.item(row, 4)
        name_item = table.item(row, 0)

        self.selected_steamid = sid_item.text() if sid_item else ""
        self.selected_name = name_item.text() if name_item else ""

        menu = QMenu(self)
        menu.addAction("Mark Cheater", lambda: self.on_mark("Cheater"))
        menu.addAction("Mark Suspicious", lambda: self.on_mark("Suspicious"))
        menu.addAction("Mark Other", lambda: self.on_mark("Other"))
        menu.addSeparator()
        menu.addAction("Edit Notes", self.on_edit_notes)
        menu.addAction("Delete User Entry", self.on_delete)
        menu.addSeparator()
        menu.addAction("View SourceBans", lambda: self.actions.view_sb(self.selected_steamid))
        menu.addAction("View TF2BD Info", lambda: self.actions.view_tf2bd(self.selected_steamid))
        menu.addAction("Open Profile", lambda: self.actions.open_profile(self.selected_steamid))
        menu.addAction("Open SteamHistory Profile", lambda: self.actions.open_sh(self.selected_steamid))
        menu.addSeparator()
        menu.addAction("Votekick player", lambda: self.actions.kick(self.selected_steamid))
        menu.addAction("Copy SteamID", lambda: self.actions.copy_id(self.selected_steamid))

        menu.exec(QCursor.pos())

    def on_mark(self, ptype):
        if self.selected_steamid:
            new_type = self.actions.mark(self.selected_steamid, self.selected_name, ptype)
            self.apply_local_update(self.selected_steamid, ptype=new_type)

    def on_edit_notes(self):
        if self.selected_steamid:
            new_note = self.actions.edit_notes(self.selected_steamid, self.selected_name)
            if new_note is not None:
                self.apply_local_update(self.selected_steamid, note=new_note)

    def on_delete(self):
        if self.selected_steamid:
            if self.actions.delete(self.selected_steamid):
                self.apply_local_update(self.selected_steamid, ptype=None, note="")

    def apply_local_update(self, steamid, ptype="NO_CHANGE", note="NO_CHANGE"):
        bg_color = None
        mark_text = "NO_CHANGE"
        if ptype != "NO_CHANGE":
            if ptype == "Cheater": bg_color = QColor(self.logic.get_setting_color('Color_Cheater'))
            elif ptype == "Suspicious": bg_color = QColor(self.logic.get_setting_color('Color_Suspicious'))
            elif ptype == "Other": bg_color = QColor(self.logic.get_setting_color('Color_Other'))
            mark_text = self.logic.lists.get_mark_label(steamid)

        for t_obj in [self.red_table, self.blue_table, self.spec_table]:
            table = t_obj['table']
            was_sorting = table.isSortingEnabled()
            table.setSortingEnabled(False)

            for r in range(table.rowCount()):
                sid_item = table.item(r, 4)
                if sid_item and sid_item.text() == steamid:
                    if ptype != "NO_CHANGE":
                        if mark_text != "NO_CHANGE":
                            table.item(r, 6).setText(mark_text)

                        for c in range(table.columnCount()):
                            item = table.item(r, c)
                            if bg_color: item.setBackground(bg_color)
                            else: item.setData(Qt.BackgroundRole, None)

                    if note != "NO_CHANGE":
                        table.item(r, 7).setText(note)

            table.setSortingEnabled(was_sorting)

    def open_settings(self): SettingsWindow(self, self.logic, self.px).exec()
    def open_userlist(self): UserListWindow(self, self.logic, self.px).exec()
    def open_recent(self): RecentPlayersWindow(self, self.logic, self.px).exec()

    def tick_update_data(self):
        if not self.is_fetching and not self.is_closing:
            self.is_fetching = True
            threading.Thread(target=self._data_worker, daemon=True).start()

    def _data_worker(self):
        try:
            res = self.logic.get_players()
            res = copy.deepcopy(res)
        except Exception as e:
            print(f"Error in data worker: {e}")
            res = ('connection_failed', [], [], [])
        if not self.is_closing:
            self.data_queue.put(res)

    def process_queue(self):
        try:
            while True:
                res = self.data_queue.get_nowait()
                self.is_fetching = False
                self.handle_data_result(res)
        except queue.Empty:
            pass

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
                steamid_status_msg = "\nSteamID not detected (Is Steam running?). Check settings."

        color = "darkcyan"
        text = ""

        if status == 'tf2_closed':
            text = "Waiting for TF2 to launch" + steamid_status_msg
            self.clear_tables()
        elif status == 'lobby_not_found':
            text = f"RCON connected." + steamid_status_msg
            color = "green"
            self.clear_tables()
        elif status == 'connection_failed':
            text = (
                "TF2 Found but RCon is unreachable. Check launch options/settings" + steamid_status_msg
            )
            color = "orange"
        elif status == 'banned':
            text = "RCON Banned (Restart TF2)" + steamid_status_msg
            color = "red"
            self.clear_tables()
        elif status == 'auth_failed':
            text = "RCON Error: Wrong Password.\nCheck TF2's launch options & Settings > RCon Password"
            color = "orange"
            self.clear_tables()
        else:
            _, red, blue, spec = result
            self.update_table(self.red_table['table'], red)
            self.update_table(self.blue_table['table'], blue)
            self.update_table(self.spec_table['table'], spec)

            total = len(red) + len(blue) + len(spec)
            player_word = "player" if total == 1 else "players"

            if steamid_status_msg:
                text = f"Connected. Monitoring {total} {player_word}. {steamid_status_msg}"
                color = "orange"
            else:
                text = f"Connected. Monitoring {total} {player_word}."
                color = "green"

        self.lbl_status.setText(text)

        css_col = "white"
        if color == "darkcyan": css_col = "#008B8B"
        elif color == "green": css_col = "#00FF00"
        elif color == "orange": css_col = "#FFA500"
        elif color == "red": css_col = "#FF5555"

        self.lbl_status.setStyleSheet(f"color: {css_col}; font-weight: bold;")

    def clear_tables(self):
        for t in [self.red_table, self.blue_table, self.spec_table]:
            t['table'].setRowCount(0)

    def update_table(self, table, players):
        was_sorting = table.isSortingEnabled()
        table.setSortingEnabled(False)

        existing_map = {}
        for r in range(table.rowCount()):
            item_sid = table.item(r, 4)
            if item_sid: existing_map[item_sid.text()] = r

        c_self = QColor(self.logic.get_setting_color('Color_Self'))
        c_cheat = QColor(self.logic.get_setting_color('Color_Cheater'))
        c_sus = QColor(self.logic.get_setting_color('Color_Suspicious'))
        c_oth = QColor(self.logic.get_setting_color('Color_Other'))
        my_sid = self.logic.get_current_user_steamid3()

        processed_sids = set()

        sus_bans_set = getattr(self.logic, 'suspicious_steamids', set())

        for p in players:
            processed_sids.add(p.steamid)

            bans = str(self.logic.get_sourcebans_count(p.steamid))
            mark = self.logic.lists.get_mark_label(p.steamid)

            bg_color = None
            if p.steamid == my_sid: bg_color = c_self
            elif p.player_type == "Cheater": bg_color = c_cheat
            elif p.player_type == "Suspicious": bg_color = c_sus
            elif p.player_type == "Other": bg_color = c_oth

            def update_cell(r, c, val, is_numeric=False):
                item = table.item(r, c)
                if not item:
                    item = NumericTableWidgetItem(val) if is_numeric else QTableWidgetItem(val)
                    item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(r, c, item)

                if c == 5 and p.steamid in sus_bans_set:
                    target_val = val + " !!"
                    if item.text() != target_val:
                        item.setText(target_val)
                        f = item.font()
                        f.setBold(True)
                        item.setFont(f)
                        item.setToolTip("Suspicious keywords found in ban history")
                else:
                    if item.text() != val:
                        item.setText(val)
                    if c == 5:
                        f = item.font()
                        f.setBold(False)
                        item.setFont(f)
                        item.setToolTip("")

                cur_bg = item.background().color()
                if bg_color:
                    if cur_bg != bg_color: item.setBackground(bg_color)
                else:
                    if cur_bg.isValid() and cur_bg.alpha() > 0:
                        item.setData(Qt.BackgroundRole, None)

            if p.steamid in existing_map:
                row = existing_map[p.steamid]
                update_cell(row, 0, str(p.name))
                update_cell(row, 1, str(p.ping), True)
                update_cell(row, 2, str(p.kills), True)
                update_cell(row, 3, str(p.deaths), True)
                update_cell(row, 4, str(p.steamid))
                update_cell(row, 5, bans, True)
                update_cell(row, 6, mark)
                update_cell(row, 7, str(p.notes or ""))
            else:
                row = table.rowCount()
                table.insertRow(row)
                update_cell(row, 0, str(p.name))
                update_cell(row, 1, str(p.ping), True)
                update_cell(row, 2, str(p.kills), True)
                update_cell(row, 3, str(p.deaths), True)
                update_cell(row, 4, str(p.steamid))
                update_cell(row, 5, bans, True)
                update_cell(row, 6, mark)
                update_cell(row, 7, str(p.notes or ""))

        for r in range(table.rowCount() - 1, -1, -1):
            sid_item = table.item(r, 4)
            if sid_item and sid_item.text() not in processed_sids:
                table.removeRow(r)

        table.setSortingEnabled(was_sorting)
