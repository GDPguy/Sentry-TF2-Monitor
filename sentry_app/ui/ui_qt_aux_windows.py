import datetime
import webbrowser
import time
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QHeaderView, QMenu,
    QFileDialog, QAbstractItemView, QApplication,
    QLineEdit, QLabel
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QCursor

from .ui_qt_dialogs import custom_popup
from .ui_qt_shared import (
    SentryTable, ActionHandler, DeselectableWindowMixin,
    NumericTableWidgetItem
)
from ..utils import convert_steamid3_to_steamid64


UL_COL_NAME = 0
UL_COL_STEAMID = 1
UL_COL_TYPE = 2
UL_COL_ADDED = 3
UL_COL_SEEN = 4
UL_COL_NOTES = 5

RP_COL_NAME = 0
RP_COL_STEAMID = 1
RP_COL_MARK = 2
RP_COL_NOTES = 3

class BaseAuxWindow(DeselectableWindowMixin, QDialog):
    def __init__(
        self, parent, logic, title, w, h, px_func,
        *, steamid_col, name_col, mark_col=None, notes_col=None
    ):
        super().__init__(parent)
        self.logic = logic
        self.px = px_func
        self.actions = ActionHandler(self, logic)

        self.steamid_col = steamid_col
        self.name_col = name_col
        self.mark_col = mark_col
        self.notes_col = notes_col

        self.pending_edits = {}

        self.setWindowTitle(title)
        self.resize(self.px(w), self.px(h))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.layout = QVBoxLayout(self)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter...")
        self.search_input.textChanged.connect(self.filter_table)
        search_layout.addWidget(self.search_input)
        self.layout.addLayout(search_layout)

        self.table = SentryTable()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)

        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.on_context_menu)
        self.table.cellDoubleClicked.connect(self.on_double_click)

        self.layout.addWidget(self.table)
        self.sel_sid = None
        self.sel_name = None

    def setup_columns(self, columns):
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)

    def filter_table(self, text):
        text = text.lower()
        for r in range(self.table.rowCount()):
            match = False
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item and text in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(r, not match)

    def on_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item: return

        row = item.row()
        self.table.selectRow(row)

        sid_item = self.table.item(row, self.steamid_col)
        name_item = self.table.item(row, self.name_col)

        if sid_item:
            self.sel_sid = sid_item.text()
            self.sel_name = name_item.text() if name_item else "Unknown"
            self.show_context_menu(QCursor.pos())

    def on_double_click(self, row, col):
        if self.notes_col is not None and col == self.notes_col:
            sid_item = self.table.item(row, self.steamid_col)
            name_item = self.table.item(row, self.name_col)
            if sid_item:
                self.sel_sid = sid_item.text()
                self.sel_name = name_item.text() if name_item else "Unknown"
                self.on_edit_notes()

    def show_context_menu(self, global_pos):
        pass

    def register_edit(self, steamid):
        self.pending_edits[steamid] = time.time() + 2.0

    def apply_local_update(self, steamid, ptype="NO_CHANGE", note="NO_CHANGE"):
        self.register_edit(steamid)

        bg_color = None
        text_color = None
        mark_text = None
        mark_tooltip = None

        if ptype == "CLEAR":
            mark_text = ""
            mark_tooltip = None
            bg_color = None
            text_color = None
        elif ptype != "NO_CHANGE":
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

        is_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)

        for r in range(self.table.rowCount()):
            sid_item = self.table.item(r, self.steamid_col)
            if not sid_item or sid_item.text() != steamid:
                continue

            if self.mark_col is not None:
                m_item = self.table.item(r, self.mark_col)
                if mark_text is not None: m_item.setText(mark_text)
                if mark_tooltip is not None: m_item.setToolTip(mark_tooltip)
                if text_color: m_item.setForeground(text_color)
                else: m_item.setData(Qt.ForegroundRole, None)

            name_item = self.table.item(r, self.name_col)
            if bg_color: name_item.setBackground(bg_color)
            else: name_item.setData(Qt.BackgroundRole, None)

            if note != "NO_CHANGE" and self.notes_col is not None:
                self.table.item(r, self.notes_col).setText(note)

        self.table.setSortingEnabled(is_sorting)

class UserListWindow(BaseAuxWindow):
    def __init__(self, parent, logic, px_func):
        super().__init__(
            parent, logic, "User List Manager", 900, 500, px_func,
            steamid_col=UL_COL_STEAMID,
            name_col=UL_COL_NAME,
            mark_col=UL_COL_TYPE,
            notes_col=UL_COL_NOTES
        )

        self.setup_columns(["Name", "SteamID", "Type", "Added", "Seen", "Notes"])

        self.table.setColumnWidth(UL_COL_NAME, self.px(150))
        self.table.setColumnWidth(UL_COL_STEAMID, self.px(130))
        self.table.setColumnWidth(UL_COL_TYPE, self.px(80))
        self.table.setColumnWidth(UL_COL_ADDED, self.px(90))
        self.table.setColumnWidth(UL_COL_SEEN, self.px(90))

        btn_layout = QHBoxLayout()
        export_btn = QPushButton("Export list to TF2BD format")
        export_btn.clicked.connect(self.export_list)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)

        btn_layout.addWidget(export_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        self.layout.addLayout(btn_layout)

        self.refresh()

    def show_context_menu(self, global_pos):
        menu = QMenu(self)
        mark_menu = menu.addMenu("Mark Player As...")
        mark_menu.addAction("Cheater", lambda: self.on_mark("Cheater"))
        mark_menu.addAction("Suspicious", lambda: self.on_mark("Suspicious"))
        mark_menu.addAction("Other", lambda: self.on_mark("Other"))
        menu.addAction("Edit Notes", self.on_edit_notes)
        menu.addAction("Delete Entry", self.on_delete)
        menu.addSeparator()
        menu.addAction("View TF2BD Info", lambda: self.actions.view_tf2bd(self.sel_sid))
        menu.addAction("Copy SteamID", lambda: self.actions.copy_id(self.sel_sid))
        menu.addAction("Open Profile", lambda: self.actions.open_profile(self.sel_sid))
        menu.addAction("Open SteamHistory Profile", lambda: self.actions.open_sh(self.sel_sid))
        menu.exec(global_pos)

    def on_mark(self, ptype):
        if self.sel_sid:
            new_type = self.actions.mark(self.sel_sid, self.sel_name, ptype)
            self.apply_local_update(self.sel_sid, ptype=new_type)

    def on_edit_notes(self):
        new_note = self.actions.edit_notes(self.sel_sid, self.sel_name)
        if new_note is not None:
            self.apply_local_update(self.sel_sid, note=new_note)

    def on_delete(self):
        if self.actions.delete(self.sel_sid):
            self.refresh()

    def refresh(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        entries = self.logic.lists.user_entries
        entries.sort(key=lambda x: x.get('time_added', 0), reverse=True)

        c_cheat = QColor(self.logic.get_setting_color('Color_Cheater'))
        c_sus = QColor(self.logic.get_setting_color('Color_Suspicious'))
        c_oth = QColor(self.logic.get_setting_color('Color_Other'))

        for e in entries:
            row = self.table.rowCount()
            self.table.insertRow(row)

            ts_add = e.get('time_added', 0)
            ts_see = e.get('time_last_seen', 0)
            d_add = datetime.datetime.fromtimestamp(ts_add).strftime('%Y-%m-%d') if ts_add else "-"
            d_see = datetime.datetime.fromtimestamp(ts_see).strftime('%Y-%m-%d') if ts_see else "-"

            items = [
                str(e.get('last_seen_name', '')),
                str(e.get('steamid', '')),
                str(e.get('player_type', '')),
                d_add, d_see,
                str(e.get('notes', ''))
            ]

            bg_color = None
            ptype = e.get('player_type')
            if ptype == 'Cheater': bg_color = c_cheat
            elif ptype == 'Suspicious': bg_color = c_sus
            elif ptype == 'Other': bg_color = c_oth

            for col, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                if col == UL_COL_NAME and bg_color:
                     item.setBackground(bg_color)
                self.table.setItem(row, col, item)

        self.table.setSortingEnabled(True)

    def export_list(self):
        fn, _ = QFileDialog.getSaveFileName(self, "Export TF2BD", "playerlist.sentry_export.json", "JSON Files (*.json)")
        if fn:
            if not fn.lower().endswith(".json"): fn += ".json"
            ok, msg = self.logic.lists.export_to_tf2bd(fn)
            custom_popup(self, None, "Export Result", msg)


class RecentPlayersWindow(BaseAuxWindow):
    def __init__(self, parent, logic, px_func):
        super().__init__(
            parent, logic, "Recent Players", 600, 400, px_func,
            steamid_col=RP_COL_STEAMID,
            name_col=RP_COL_NAME,
            mark_col=RP_COL_MARK,
            notes_col=RP_COL_NOTES
        )

        self.setup_columns(["Name", "SteamID", "Mark", "Notes"])
        self.table.setColumnWidth(RP_COL_NAME, self.px(180))
        self.table.setColumnWidth(RP_COL_STEAMID, self.px(130))
        self.table.setColumnWidth(RP_COL_MARK, self.px(80))

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        btn_layout.addWidget(close)
        self.layout.addLayout(btn_layout)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self.refresh()

    def closeEvent(self, event):
        if self.timer.isActive(): self.timer.stop()
        super().closeEvent(event)

    def show_context_menu(self, global_pos):
        menu = QMenu(self)
        mark_menu = menu.addMenu("Mark Player As...")
        mark_menu.addAction("Cheater", lambda: self.on_mark("Cheater"))
        mark_menu.addAction("Suspicious", lambda: self.on_mark("Suspicious"))
        mark_menu.addAction("Other", lambda: self.on_mark("Other"))
        menu.addAction("Edit Notes", self.on_edit_notes)
        menu.addAction("Delete User Entry", self.on_delete)
        menu.addSeparator()
        menu.addAction("View TF2BD Info", lambda: self.actions.view_tf2bd(self.sel_sid))
        menu.addAction("Copy SteamID", lambda: self.actions.copy_id(self.sel_sid))
        menu.addAction("Open Profile", lambda: self.actions.open_profile(self.sel_sid))
        menu.addAction("Open SteamHistory Profile", lambda: self.actions.open_sh(self.sel_sid))
        menu.exec(global_pos)

    def on_mark(self, ptype):
        if self.sel_sid:
            self.logic.mark_recently_played(self.sel_sid, ptype, self.logic.recently_played)
            self.apply_local_update(self.sel_sid, ptype=ptype)

    def on_edit_notes(self):
        new_note = self.actions.edit_notes(self.sel_sid, self.sel_name)
        if new_note is not None:
             self.apply_local_update(self.sel_sid, note=new_note)

    def on_delete(self):
        if self.sel_sid:
            if self.actions.delete(self.sel_sid):
                self.apply_local_update(self.sel_sid, ptype="CLEAR", note="")

    def refresh(self):
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)

        v_scroll = self.table.verticalScrollBar().value()
        players = self.logic.get_recently_played_snapshot()
        now = time.time()

        existing_map = {}
        for r in range(self.table.rowCount()):
            item_sid = self.table.item(r, self.steamid_col)
            if item_sid: existing_map[item_sid.text()] = r

        c_self = QColor(self.logic.get_setting_color('Color_Self'))
        c_cheat = QColor(self.logic.get_setting_color('Color_Cheater'))
        c_sus = QColor(self.logic.get_setting_color('Color_Suspicious'))
        c_oth = QColor(self.logic.get_setting_color('Color_Other'))
        my_sid = self.logic.get_current_user_steamid3()

        processed_sids = set()
        for p in players:
            processed_sids.add(p.steamid)

            is_pending = False
            if p.steamid in self.pending_edits:
                if now < self.pending_edits[p.steamid]: is_pending = True
                else: del self.pending_edits[p.steamid]

            mark = self.logic.lists.get_mark_label(p.steamid)
            tooltip = self.logic.lists.get_mark_tooltip(p.steamid)
            real_notes = self.logic.lists.get_user_notes(p.steamid)

            items = {
                RP_COL_NAME: p.name,
                RP_COL_STEAMID: p.steamid,
                RP_COL_MARK: mark,
                RP_COL_NOTES: real_notes
            }

            raw_type = self.logic.lists.identify_player_type(p.steamid)
            bg_color = None
            text_color = None

            if p.steamid == my_sid: bg_color = c_self
            elif raw_type == "Cheater":
                bg_color = c_cheat
                text_color = c_cheat
            elif raw_type == "Suspicious":
                bg_color = c_sus
                text_color = c_sus
            elif raw_type == "Other":
                bg_color = c_oth
                text_color = c_oth

            if p.steamid in existing_map:
                row = existing_map[p.steamid]
                for col, val in items.items():
                    item = self.table.item(row, col)
                    if not is_pending:
                        if item.text() != val: item.setText(val)
                        if col == self.mark_col: item.setToolTip(tooltip)

                    if col == self.name_col:
                        cur_bg = item.background().color()
                        if bg_color:
                            if cur_bg != bg_color: item.setBackground(bg_color)
                        else:
                            if cur_bg.isValid() and cur_bg.alpha() > 0: item.setData(Qt.BackgroundRole, None)
                    elif col == self.mark_col:
                        if text_color: item.setForeground(text_color)
                        else: item.setData(Qt.ForegroundRole, None)
                    else:
                        item.setData(Qt.BackgroundRole, None)
            else:
                row = self.table.rowCount()
                self.table.insertRow(row)
                for col, val in items.items():
                    item = QTableWidgetItem(val)
                    item.setTextAlignment(Qt.AlignCenter)
                    if col == self.name_col and bg_color: item.setBackground(bg_color)
                    if col == self.mark_col:
                        item.setToolTip(tooltip)
                        if text_color: item.setForeground(text_color)
                    self.table.setItem(row, col, item)

        for r in range(self.table.rowCount() - 1, -1, -1):
            sid_item = self.table.item(r, self.steamid_col)
            if sid_item and sid_item.text() not in processed_sids:
                self.table.removeRow(r)

        self.table.verticalScrollBar().setValue(v_scroll)
        self.table.setSortingEnabled(was_sorting)
        if self.search_input.text(): self.filter_table(self.search_input.text())
