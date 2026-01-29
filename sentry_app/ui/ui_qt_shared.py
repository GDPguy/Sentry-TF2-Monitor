import datetime
import webbrowser
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QPushButton, QTextEdit,
                               QTableWidget, QApplication, QHBoxLayout,
                               QTableWidgetItem, QHeaderView, QMenu)
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor

from .ui_qt_dialogs import custom_popup, custom_edit_multiline
from ..utils import convert_steamid3_to_steamid64

class NumericTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        d1 = self.data(Qt.UserRole)
        d2 = other.data(Qt.UserRole)

        v1 = float(d1) if d1 is not None else -1.0
        v2 = float(d2) if d2 is not None else -1.0

        return v1 < v2

class TextViewer(QDialog):
    def __init__(self, parent, title, text):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(700, 450)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)

        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(text)
        layout.addWidget(txt)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn = QPushButton("Close")
        btn.setFixedWidth(100)
        btn.clicked.connect(self.close)
        btn_layout.addWidget(btn)

        layout.addLayout(btn_layout)

class SentryTable(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.ClickFocus)

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        if not index.isValid():
            self.clearSelection()
            self.clearFocus()
        super().mousePressEvent(event)

class DeselectableWindowMixin:
    def mousePressEvent(self, event):
        focused_widget = QApplication.focusWidget()
        if isinstance(focused_widget, QTableWidget):
            focused_widget.clearSelection()
            focused_widget.clearFocus()
        super().mousePressEvent(event)

class ActionHandler:
    def __init__(self, parent_window, logic):
        self.parent = parent_window
        self.logic = logic

    def mark(self, steamid, name, ptype):
        self.logic.mark_player(steamid, ptype, name=name)
        return ptype

    def edit_notes(self, steamid, name):
        curr = self.logic.lists.get_user_notes(steamid)
        new_note = custom_edit_multiline(self.parent, None, "Edit Notes", "Enter notes:", initialvalue=curr)
        if new_note is not None:
            ptype = self.logic.lists.identify_player_type(steamid) or "Other"
            self.logic.mark_player(steamid, ptype, notes=new_note, name=name)
            return new_note
        return None

    def delete(self, steamid):
        if custom_popup(self.parent, None, "Confirm", f"Delete entry for {steamid}?", is_confirmation=True):
            self.logic.delete_player(steamid)
            return True
        return False

    def kick(self, steamid, reason=""):
        self.logic.kick_player(steamid, reason)

    def open_profile(self, steamid):
        s64 = convert_steamid3_to_steamid64(steamid)
        if s64: webbrowser.open(f"https://steamcommunity.com/profiles/{s64}")

    def open_sh(self, steamid):
        s64 = convert_steamid3_to_steamid64(steamid)
        if s64: webbrowser.open(f"https://steamhistory.net/id/{s64}")

    def copy_id(self, steamid):
        QApplication.clipboard().setText(steamid)

    def view_sb(self, steamid):
        data = self.logic.get_sourcebans_details(steamid)
        if not data:
            custom_popup(self.parent, None, "SourceBans", "No recent SourceBan data found.")
            return
        lines = []
        for b in data:
            bd = datetime.datetime.fromtimestamp(b.get('BanTimestamp', 0)).strftime('%Y-%m-%d')
            lines.append(f"Date: {bd}\nServer: {b.get('Server')}\nReason: {b.get('BanReason')}\nState: {b.get('CurrentState')}\n")
        TextViewer(self.parent, f"SourceBans - {steamid}", "\n".join(lines)).exec()

    def view_tf2bd(self, steamid):
        notes = self.logic.lists.get_tf2bd_notes(steamid)
        if not notes or not notes.strip():
            custom_popup(self.parent, None, "TF2BD Info", "No TF2BD data found for this player.")
            return
        TextViewer(self.parent, f"TF2BD Info - {steamid}", notes).exec()
