from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton,
                               QHBoxLayout, QLineEdit, QTextEdit)
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

class CustomNoteDialog(QDialog):
    def __init__(self, parent, title, prompt, initial_value=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.input_text = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(prompt))

        self.text_area = QTextEdit()
        self.text_area.setPlainText(initial_value)
        self.text_area.setAcceptRichText(False)
        layout.addWidget(self.text_area)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_ok = QPushButton("Save")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept_input)
        btn_layout.addWidget(btn_ok)

        layout.addLayout(btn_layout)
        self.resize(400, 300)

    def accept_input(self):
        self.input_text = self.text_area.toPlainText()
        self.accept()

def custom_edit_multiline(parent, px_func, title, prompt, initialvalue=""):
    dlg = CustomNoteDialog(parent, title, prompt, initialvalue)
    if dlg.exec():
        return dlg.input_text
    return None
