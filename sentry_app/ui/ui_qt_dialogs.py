from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton,
                               QHBoxLayout, QLineEdit, QTextEdit, QRadioButton,
                               QButtonGroup, QGroupBox)
from PySide6.QtCore import Qt

class CustomPopup(QDialog):
    def __init__(self, parent, title, message, is_confirmation=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.result_value = False
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        lbl = QLabel(message)
        lbl.setWordWrap(True)
        lbl.setMinimumWidth(300)
        lbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        layout.addWidget(lbl)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        if is_confirmation:
            btn_no = QPushButton("No")
            btn_no.clicked.connect(self.reject)
            btn_layout.addWidget(btn_no)

            btn_yes = QPushButton("Yes")
            btn_yes.setDefault(True)
            btn_yes.clicked.connect(self.accept_action)
            btn_layout.addWidget(btn_yes)
        else:
            btn_ok = QPushButton("OK")
            btn_ok.setDefault(True)
            btn_ok.clicked.connect(self.accept_action)
            btn_layout.addWidget(btn_ok)

        layout.addLayout(btn_layout)

    def accept_action(self):
        self.result_value = True
        self.accept()

def custom_popup(parent, px_func, title, message, is_confirmation=False):
    dlg = CustomPopup(parent, title, message, is_confirmation)
    dlg.exec()
    return dlg.result_value

class CustomAskString(QDialog):
    def __init__(self, parent, title, prompt, initial_value=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.input_text = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(prompt))

        self.entry = QLineEdit()
        self.entry.setText(initial_value)
        self.entry.selectAll()
        layout.addWidget(self.entry)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_ok = QPushButton("OK")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept_input)
        btn_layout.addWidget(btn_ok)

        layout.addLayout(btn_layout)
        self.setMinimumWidth(300)

    def accept_input(self):
        self.input_text = self.entry.text()
        self.accept()

def custom_askstring(parent, px_func, title, prompt, initialvalue=""):
    dlg = CustomAskString(parent, title, prompt, initialvalue)
    if dlg.exec():
        return dlg.input_text
    return None

class EditUserDialog(QDialog):
    def __init__(self, parent, title, name, steamid, current_notes, current_type, logic):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.result_notes = None
        self.result_type = None

        self.logic = logic
        self.steamid = steamid
        self.was_deleted = False

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        lbl_name = QLabel(f"Player: {name}")
        lbl_name.setStyleSheet("font-weight: bold")
        layout.addWidget(lbl_name)

        lbl_id = QLabel(f"SteamID: {steamid}")
        layout.addWidget(lbl_id)

        layout.addWidget(QLabel("Player Type:"))
        hbox = QHBoxLayout()
        self.bg = QButtonGroup(self)

        col_cheat = logic.get_setting_color('Color_Cheater')
        col_sus = logic.get_setting_color('Color_Suspicious')
        col_other = logic.get_setting_color('Color_Other')

        self.rb_cheat = QRadioButton("Cheater")
        self.rb_cheat.setStyleSheet(f"color: {col_cheat}; font-weight: bold;")
        self.bg.addButton(self.rb_cheat)
        hbox.addWidget(self.rb_cheat)

        self.rb_sus = QRadioButton("Suspicious")
        self.rb_sus.setStyleSheet(f"color: {col_sus}; font-weight: bold;")
        self.bg.addButton(self.rb_sus)
        hbox.addWidget(self.rb_sus)

        self.rb_other = QRadioButton("Other")
        self.rb_other.setStyleSheet(f"color: {col_other};")
        self.bg.addButton(self.rb_other)
        hbox.addWidget(self.rb_other)

        layout.addLayout(hbox)

        if current_type == "Cheater": self.rb_cheat.setChecked(True)
        elif current_type == "Suspicious": self.rb_sus.setChecked(True)
        else: self.rb_other.setChecked(True)

        layout.addWidget(QLabel("Notes:"))
        self.text_area = QTextEdit()
        self.text_area.setPlainText(current_notes)
        self.text_area.setAcceptRichText(False)
        layout.addWidget(self.text_area)

        btn_layout = QHBoxLayout()

        btn_delete = QPushButton("Delete Entry")
        btn_delete.clicked.connect(self.on_delete)
        btn_layout.addWidget(btn_delete)

        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_ok = QPushButton("Save")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept_input)
        btn_layout.addWidget(btn_ok)

        layout.addLayout(btn_layout)
        self.resize(450, 450)

    def accept_input(self):
        self.result_notes = self.text_area.toPlainText()
        if self.rb_cheat.isChecked(): self.result_type = "Cheater"
        elif self.rb_sus.isChecked(): self.result_type = "Suspicious"
        else: self.result_type = "Other"
        self.accept()

    def on_delete(self):
        ok = custom_popup(self, None, "Confirm Delete", "Delete this user entry?", is_confirmation=True)
        if ok:
            self.logic.delete_player(self.steamid)
            self.was_deleted = True
            self.accept()

def custom_edit_user(parent, title, name, steamid, current_notes, current_type, logic):
    dlg = EditUserDialog(parent, title, name, steamid, current_notes, current_type, logic)
    if dlg.exec():
        if dlg.was_deleted:
            return "DELETED", None
        return dlg.result_notes, dlg.result_type
    return None, None
