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
from PySide6.QtCore import Qt, QTimer, QUrl, QSize
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QPixmap, QIcon
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from .ui_qt_settings import SettingsWindow
from .ui_qt_aux_windows import UserListWindow, RecentPlayersWindow
from .ui_qt_dialogs import custom_popup
from .ui_qt_shared import SentryTable, ActionHandler, DeselectableWindowMixin, NumericTableWidgetItem
from ..consts import APP_VERSION

COL_STACK = 0
COL_NAME = 1
COL_PING = 2
COL_KILLS = 3
COL_DEATHS = 4
COL_STEAMID = 5
COL_AGE = 6
COL_HOURS = 7
COL_VAC = 8
COL_GAME_BANS = 9
COL_SBANS = 10
COL_MARK = 11
COL_NOTES = 12

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

        self.nam = QNetworkAccessManager()
        self.icon_cache = {}

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
        w, h = self.px(950), self.px(950)
        self.resize(w, h)
        self.setMinimumSize(self.px(600), self.px(400))

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 0, 5, 8)

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
        font = lbl_title.font()
        font.setBold(True)
        lbl_title.setFont(font)
        lbl_title.setIndent(2)
        layout.addWidget(lbl_title)

        table = SentryTable()
        cols = ['#', 'Name', 'Ping', 'Kills', 'Deaths', 'SteamID', 'Age', 'Hours', 'VAC', 'GameBans', 'SourceBans', 'Mark', 'Notes']

        table.setColumnCount(len(cols))
        table.setHorizontalHeaderLabels(cols)
        table.verticalHeader().setDefaultSectionSize(self.px(28))
        table.setIconSize(QSize(self.px(24), self.px(24)))
        table.setSortingEnabled(True)

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)

        widths = [40, 180, 40, 40, 50, 130, 40, 45, 40, 75, 80, 60, 0]

        show_sid = self.logic.get_setting_bool("Show_SteamID_Column")
        if not show_sid:
            table.setColumnHidden(COL_STEAMID, True)

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
        sid_item = table.item(row, COL_STEAMID)
        name_item = table.item(row, COL_NAME)
        steamid = sid_item.text() if sid_item else None

        if col == COL_NOTES and steamid:
            self.selected_steamid = steamid
            self.selected_name = name_item.text() if name_item else ""
            self.on_edit_notes()
        elif col == COL_SBANS and steamid:
            self.actions.view_sb(steamid)

    def on_context_menu(self, pos, table):
        item = table.itemAt(pos)
        if not item: return

        row = item.row()
        table.selectRow(row)

        sid_item = table.item(row, COL_STEAMID)
        name_item = table.item(row, COL_NAME)

        self.selected_steamid = sid_item.text() if sid_item else ""
        self.selected_name = name_item.text() if name_item else ""

        menu = QMenu(self)

        mark_menu = menu.addMenu("Mark Player As...")
        mark_menu.addAction("Cheater", lambda: self.on_mark("Cheater"))
        mark_menu.addAction("Suspicious", lambda: self.on_mark("Suspicious"))
        mark_menu.addAction("Other", lambda: self.on_mark("Other"))

        menu.addAction("Edit Notes", self.on_edit_notes)
        menu.addAction("Delete User Entry", self.on_delete)
        menu.addSeparator()
        menu.addAction("View SourceBans", lambda: self.actions.view_sb(self.selected_steamid))
        menu.addAction("View TF2BD Info", lambda: self.actions.view_tf2bd(self.selected_steamid))
        menu.addAction("Open Profile", lambda: self.actions.open_profile(self.selected_steamid))
        menu.addAction("Open SteamHistory Profile", lambda: self.actions.open_sh(self.selected_steamid))
        menu.addSeparator()
        kick_menu = menu.addMenu("Votekick Player...")
        kick_menu.addAction("Kick (No Reason)", lambda: self.actions.kick(self.selected_steamid, ""))
        kick_menu.addAction("Kick: Cheating", lambda: self.actions.kick(self.selected_steamid, "cheating"))
        kick_menu.addAction("Kick: Idle", lambda: self.actions.kick(self.selected_steamid, "idle"))
        kick_menu.addAction("Kick: Scamming", lambda: self.actions.kick(self.selected_steamid, "scamming"))
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
        text_color = None

        if ptype != "NO_CHANGE":
            if ptype == "Cheater":
                bg_color = QColor(self.logic.get_setting_color('Color_Cheater'))
                text_color = bg_color
            elif ptype == "Suspicious":
                bg_color = QColor(self.logic.get_setting_color('Color_Suspicious'))
                text_color = bg_color
            elif ptype == "Other":
                bg_color = QColor(self.logic.get_setting_color('Color_Other'))
                text_color = bg_color

            mark_text = self.logic.lists.get_mark_label(steamid)
            mark_tooltip = self.logic.lists.get_mark_tooltip(steamid)
        else:
            mark_tooltip = None

        for t_obj in [self.red_table, self.blue_table, self.spec_table]:
            table = t_obj['table']
            was_sorting = table.isSortingEnabled()
            table.setSortingEnabled(False)

            for r in range(table.rowCount()):
                sid_item = table.item(r, COL_STEAMID)
                if sid_item and sid_item.text() == steamid:
                    if ptype != "NO_CHANGE":
                        if mark_text != "NO_CHANGE":
                            m_item = table.item(r, COL_MARK)
                            m_item.setText(mark_text)
                            m_item.setToolTip(mark_tooltip)

                        for c in range(table.columnCount()):
                            item = table.item(r, c)
                            if c == COL_NAME:
                                if bg_color: item.setBackground(bg_color)
                                else: item.setData(Qt.BackgroundRole, None)
                            elif c == COL_MARK:
                                if text_color: item.setForeground(text_color)
                                else: item.setData(Qt.ForegroundRole, None)
                            else:
                                item.setData(Qt.BackgroundRole, None)

                    if note != "NO_CHANGE":
                        table.item(r, COL_NOTES).setText(note)

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


    def set_avatar(self, item, url):
        if not url: return

        if url in self.icon_cache:
            item.setIcon(self.icon_cache[url])
            return

        req = QNetworkRequest(QUrl(url))
        reply = self.nam.get(req)

        def handle_load():
            if reply.error() == QNetworkReply.NoError:
                data = reply.readAll()
                pix = QPixmap()
                if pix.loadFromData(data):
                    icon = QIcon(pix)
                    self.icon_cache[url] = icon
                    try:
                        item.setIcon(icon)
                    except (RuntimeError, AttributeError):
                        pass
            reply.deleteLater()
        reply.finished.connect(handle_load)

    def update_table(self, table, players):
        was_sorting = table.isSortingEnabled()
        table.setSortingEnabled(False)

        existing_map = {}
        for r in range(table.rowCount()):
            item_sid = table.item(r, COL_STEAMID)
            if item_sid: existing_map[item_sid.text()] = r

        c_self = QColor(self.logic.get_setting_color('Color_Self'))
        c_cheat = QColor(self.logic.get_setting_color('Color_Cheater'))
        c_sus = QColor(self.logic.get_setting_color('Color_Suspicious'))
        c_oth = QColor(self.logic.get_setting_color('Color_Other'))
        my_sid = self.logic.get_current_user_steamid3()
        sus_bans_set = getattr(self.logic, 'suspicious_steamids', set())

        def update_cell(r, c, text_val, sort_val=None, bg=None, is_numeric=False, tooltip=None):
            item = table.item(r, c)
            if not item:
                if is_numeric: item = NumericTableWidgetItem(str(text_val))
                else: item = QTableWidgetItem(str(text_val))
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(r, c, item)

            if item.text() != str(text_val): item.setText(str(text_val))
            if sort_val is not None: item.setData(Qt.UserRole, sort_val)

            if bg: item.setBackground(bg)
            else: item.setData(Qt.BackgroundRole, None)

            if tooltip: item.setToolTip(tooltip)
            else: item.setToolTip("")
            return item

        processed_sids = set()
        for p in players:
            processed_sids.add(p.steamid)

            status_bg = None
            status_fg = None

            if p.steamid == my_sid: status_bg = c_self
            elif p.player_type == "Cheater":
                status_bg = c_cheat
                status_fg = c_cheat
            elif p.player_type == "Suspicious":
                status_bg = c_sus
                status_fg = c_sus
            elif p.player_type == "Other":
                status_bg = c_oth
                status_fg = c_oth

            if p.steamid in existing_map:
                row = existing_map[p.steamid]
            else:
                row = table.rowCount()
                table.insertRow(row)

            stack_txt = f"[{p.stack_id}]" if p.stack_id else ""

            stack_tip = ""
            if p.stack_id:
                stack_lines = [f"Linked Group #{p.stack_id}"]
                if p.direct_friends:
                    stack_lines.append(f"Direct Friends: {', '.join(p.direct_friends)}")
                if p.extended_stack:
                    stack_lines.append(f"Indirectly Linked: {', '.join(p.extended_stack)}")
                stack_tip = "\n".join(stack_lines)

            s_item = update_cell(row, COL_STACK, stack_txt, sort_val=p.stack_id, bg=None, is_numeric=True, tooltip=stack_tip)

            if p.stack_id:
                colors = ["#0000FF", "#FF00FF", "#CC0000", "#008000", "#FFA500", "#1E90FF"]
                c_hex = colors[p.stack_id % len(colors)]
                s_item.setForeground(QColor(c_hex))
            else:
                s_item.setData(Qt.ForegroundRole, None)

            name_item = update_cell(row, COL_NAME, p.name, bg=status_bg)
            if p.avatar_url: self.set_avatar(name_item, p.avatar_url)

            update_cell(row, COL_PING, p.ping, sort_val=p.ping, bg=None, is_numeric=True)

            update_cell(row, COL_KILLS, p.kills, sort_val=p.kills, bg=None, is_numeric=True)

            update_cell(row, COL_DEATHS, p.deaths, sort_val=p.deaths, bg=None, is_numeric=True)

            update_cell(row, COL_STEAMID, p.steamid, bg=None)

            age_text = f"{p.account_age}y" if p.account_age is not None else "?"
            update_cell(row, COL_AGE, age_text, sort_val=p.account_age, bg=None, is_numeric=True)

            minutes = p.tf2_playtime
            if minutes is None:
                hr_text = "?"
            elif minutes < 60:
                hr_text = "<1h"
            else:
                hr_text = f"{int(minutes / 60)}h"

            update_cell(row, COL_HOURS, hr_text, sort_val=minutes, bg=None, is_numeric=True)

            vac_text = "VAC" if p.vac_banned else ""
            vac_sort = 1 if p.vac_banned else 0
            v_item = update_cell(row, COL_VAC, vac_text, sort_val=vac_sort, bg=None, is_numeric=True)

            if p.vac_banned:
                v_item.setForeground(QColor("#ff4444"))
                f = v_item.font(); f.setBold(True); v_item.setFont(f)
            else:
                v_item.setData(Qt.ForegroundRole, None)
                f = v_item.font(); f.setBold(False); v_item.setFont(f)

            gb_text = str(p.game_bans) if p.game_bans > 0 else ""
            update_cell(row, COL_GAME_BANS, gb_text, sort_val=p.game_bans, bg=None, is_numeric=True)

            sb_text = str(p.ban_count) if p.ban_count != "" else ""
            try: sb_sort = int(p.ban_count) if p.ban_count != "" else 0
            except: sb_sort = 0

            sb_item = update_cell(row, COL_SBANS, sb_text, sort_val=sb_sort, bg=None, is_numeric=True)

            is_suspicious_bans = (p.steamid in sus_bans_set)

            f = sb_item.font()
            if is_suspicious_bans:
                f.setBold(True)
                sb_item.setForeground(QColor("#ff4444"))
                sb_item.setToolTip("Suspicious keywords found in ban history")
            elif sb_sort > 0:
                f.setBold(False)
                sb_item.setData(Qt.ForegroundRole, None)
                sb_item.setToolTip(f"{sb_sort} SourceBans found")
            else:
                f.setBold(False)
                sb_item.setData(Qt.ForegroundRole, None)
                sb_item.setToolTip("")
            sb_item.setFont(f)

            mark_item = update_cell(row, COL_MARK, p.mark_label, bg=None, tooltip=p.mark_tooltip)
            if status_fg:
                mark_item.setForeground(status_fg)
            else:
                mark_item.setData(Qt.ForegroundRole, None)

            update_cell(row, COL_NOTES, p.notes or "", bg=None)

        for r in range(table.rowCount() - 1, -1, -1):
            sid_item = table.item(r, COL_STEAMID)
            if sid_item and sid_item.text() not in processed_sids:
                table.removeRow(r)

        table.setSortingEnabled(was_sorting)
