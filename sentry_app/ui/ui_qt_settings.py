from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox,
                               QPushButton, QGroupBox, QScrollArea,
                               QWidget, QColorDialog, QFormLayout, QGridLayout)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIntValidator, QColor

from ..consts import DEFAULT_SETTINGS

class SettingsWindow(QDialog):
    def __init__(self, parent, logic, px_func):
        super().__init__(parent)
        self.logic = logic
        self.px = px_func
        self.setWindowTitle("Settings")

        self.resize(self.px(720), self.px(800))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        main_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        self.form_layout = QVBoxLayout(content_widget)
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        self.vars = {}

        grp_conn = QGroupBox("Connection / Identity")
        lay_conn = QFormLayout(grp_conn)

        self.vars['RCon_Password'] = QLineEdit(self.logic.get_setting('RCon_Password'))
        self.vars['RCon_Password'].setEchoMode(QLineEdit.Password)
        self.vars['RCon_Password'].setMaxLength(128)

        btn_show_pass = QPushButton("Show")
        btn_show_pass.setFixedWidth(self.px(80))
        btn_show_pass.clicked.connect(lambda: self.toggle_echo(self.vars['RCon_Password'], btn_show_pass))

        hb_pass = QHBoxLayout()
        hb_pass.addWidget(self.vars['RCon_Password'])
        hb_pass.addWidget(btn_show_pass)
        lay_conn.addRow("RCon Password:", hb_pass)

        self.vars['RCon_Port'] = QLineEdit(self.logic.get_setting('RCon_Port'))
        self.vars['RCon_Port'].setValidator(QIntValidator(1, 65535))
        self.vars['RCon_Port'].setFixedWidth(self.px(80))
        lay_conn.addRow("RCon Port:", self.vars['RCon_Port'])

        detect_box = QHBoxLayout()
        self.lbl_detected = QLabel("...")
        self.lbl_detected.setStyleSheet("color: gray; font-style: italic;")
        btn_detect = QPushButton("Redetect")
        btn_detect.setFixedWidth(self.px(80))
        btn_detect.clicked.connect(self.redetect)
        detect_box.addWidget(QLabel("Auto-Detected:"))
        detect_box.addWidget(self.lbl_detected)
        detect_box.addWidget(btn_detect)
        detect_box.addStretch()
        lay_conn.addRow(detect_box)

        self.vars['User'] = QLineEdit(self.logic.get_setting('User'))
        self.vars['User'].setMaxLength(32)
        self.vars['User'].setFixedWidth(self.px(200))
        lay_conn.addRow("Fallback SteamID3:", self.vars['User'])

        self.vars['Use_Manual_SteamID'] = QCheckBox("Always use this ID (Override auto-detection)")
        self.vars['Use_Manual_SteamID'].setChecked(self.logic.get_setting_bool('Use_Manual_SteamID'))
        lay_conn.addRow(self.vars['Use_Manual_SteamID'])

        self.form_layout.addWidget(grp_conn)

        grp_ext = QGroupBox("Internet / API")
        lay_ext = QFormLayout(grp_ext)

        self.vars['Steam_API_Key'] = QLineEdit(self.logic.get_setting('Steam_API_Key'))
        self.vars['Steam_API_Key'].setEchoMode(QLineEdit.Password)

        btn_show_skey = QPushButton("Show")
        btn_show_skey.setFixedWidth(self.px(80))
        btn_show_skey.clicked.connect(lambda: self.toggle_echo(self.vars['Steam_API_Key'], btn_show_skey))

        hb_skey = QHBoxLayout()
        hb_skey.addWidget(self.vars['Steam_API_Key'])
        hb_skey.addWidget(btn_show_skey)
        lay_ext.addRow("Steam Web API Key:", hb_skey)

        self.vars['SteamHistory_API_Key'] = QLineEdit(self.logic.get_setting('SteamHistory_API_Key'))
        self.vars['SteamHistory_API_Key'].setEchoMode(QLineEdit.Password)

        btn_show_api = QPushButton("Show")
        btn_show_api.setFixedWidth(self.px(80))
        btn_show_api.clicked.connect(lambda: self.toggle_echo(self.vars['SteamHistory_API_Key'], btn_show_api))

        hb_api = QHBoxLayout()
        hb_api.addWidget(self.vars['SteamHistory_API_Key'])
        hb_api.addWidget(btn_show_api)

        lay_ext.addRow("SteamHistory API Key:", hb_api)

        self.vars['Enable_Sourcebans_Lookup'] = QCheckBox("Enable SteamHistory SourceBans Lookup")
        self.vars['Enable_Sourcebans_Lookup'].setChecked(self.logic.get_setting_bool("Enable_Sourcebans_Lookup"))
        lay_ext.addRow(self.vars['Enable_Sourcebans_Lookup'])

        self.vars['Auto_Update_TF2BD_Lists'] = QCheckBox("Auto-update TF2BD lists on startup")
        self.vars['Auto_Update_TF2BD_Lists'].setChecked(self.logic.get_setting_bool("Auto_Update_TF2BD_Lists"))
        lay_ext.addRow(self.vars['Auto_Update_TF2BD_Lists'])

        self.form_layout.addWidget(grp_ext)

        grp_auto = QGroupBox("Automation")
        lay_auto = QGridLayout(grp_auto)

        self.vars['Kick_Cheaters'] = QCheckBox("Auto Kick Cheaters")
        self.vars['Kick_Cheaters'].setChecked(self.logic.get_setting_bool('Kick_Cheaters'))
        lay_auto.addWidget(self.vars['Kick_Cheaters'], 0, 0)

        lbl_kick = QLabel("Interval (s):")
        lbl_kick.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay_auto.addWidget(lbl_kick, 0, 1)

        self.vars['Kick_Cheaters_Interval'] = QSpinBox()
        self.vars['Kick_Cheaters_Interval'].setRange(5, 60)
        self.vars['Kick_Cheaters_Interval'].setValue(self.logic.get_setting_int('Kick_Cheaters_Interval'))
        lay_auto.addWidget(self.vars['Kick_Cheaters_Interval'], 0, 2)

        self.vars['Announce_Cheaters'] = QCheckBox("Global Chat Announce")
        self.vars['Announce_Cheaters'].setChecked(self.logic.get_setting_bool('Announce_Cheaters'))
        lay_auto.addWidget(self.vars['Announce_Cheaters'], 1, 0)

        lbl_ann = QLabel("Interval (s):")
        lbl_ann.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay_auto.addWidget(lbl_ann, 1, 1)

        self.vars['Announce_Cheaters_Interval'] = QSpinBox()
        self.vars['Announce_Cheaters_Interval'].setRange(5, 60)
        self.vars['Announce_Cheaters_Interval'].setValue(self.logic.get_setting_int('Announce_Cheaters_Interval'))
        lay_auto.addWidget(self.vars['Announce_Cheaters_Interval'], 1, 2)

        lay_auto.setColumnStretch(3, 1)

        self.vars['Party_Announce_Cheaters'] = QCheckBox("Announce New Cheaters to Party")
        self.vars['Party_Announce_Cheaters'].setChecked(self.logic.get_setting_bool('Party_Announce_Cheaters'))
        lay_auto.addWidget(self.vars['Party_Announce_Cheaters'], 2, 0, 1, 4)

        self.vars['Party_Announce_Bans'] = QCheckBox("Announce Suspicious SourceBans to Party")
        self.vars['Party_Announce_Bans'].setChecked(self.logic.get_setting_bool('Party_Announce_Bans'))
        lay_auto.addWidget(self.vars['Party_Announce_Bans'], 3, 0, 1, 4)

        self.form_layout.addWidget(grp_auto)

        grp_app = QGroupBox("Application Settings")
        lay_app = QFormLayout(grp_app)

        hb_save = QHBoxLayout()
        self.vars['Save_Player_Names'] = QCheckBox("Save Player Names")
        self.vars['Save_Player_Names'].setChecked(self.logic.get_setting_bool('Save_Player_Names'))
        hb_save.addWidget(self.vars['Save_Player_Names'])

        self.vars['Save_Player_Timestamps'] = QCheckBox("Save Timestamps")
        self.vars['Save_Player_Timestamps'].setChecked(self.logic.get_setting_bool('Save_Player_Timestamps'))
        hb_save.addWidget(self.vars['Save_Player_Timestamps'])
        hb_save.addStretch()
        lay_app.addRow("User List:", hb_save)

        self.vars['Show_SteamID_Column'] = QCheckBox("Show SteamID Column in Main Window (Restart Required)")
        self.vars['Show_SteamID_Column'].setChecked(self.logic.get_setting_bool('Show_SteamID_Column'))
        lay_app.addRow("Interface:", self.vars['Show_SteamID_Column'])

        self.vars['UI_Scale'] = QDoubleSpinBox()
        self.vars['UI_Scale'].setRange(0.85, 2.0)
        self.vars['UI_Scale'].setSingleStep(0.05)
        self.vars['UI_Scale'].setValue(self.logic.get_setting_float('UI_Scale'))
        self.vars['UI_Scale'].setFixedWidth(self.px(80))

        lay_app.addRow("UI Scale (Restart Required):", self.vars['UI_Scale'])

        self.color_vars = {}
        self.color_widgets = {}

        color_grid = QGridLayout()
        color_grid.setColumnStretch(4, 1)

        def add_color_row_grid(row, label_text, key):
            current_hex = self.logic.get_setting_color(key)
            self.color_vars[key] = current_hex

            color_grid.addWidget(QLabel(label_text), row, 0)

            lbl = QLabel()
            lbl.setFixedSize(self.px(50), self.px(20))
            lbl.setStyleSheet(f"background-color: {current_hex}; border: 1px solid black;")
            self.color_widgets[key] = lbl
            color_grid.addWidget(lbl, row, 1)

            btn_pick = QPushButton("Pick")
            btn_pick.setFixedWidth(self.px(60))
            btn_pick.clicked.connect(lambda: self.pick_color(key))
            color_grid.addWidget(btn_pick, row, 2)

            btn_reset = QPushButton("Reset")
            btn_reset.setFixedWidth(self.px(60))
            btn_reset.clicked.connect(lambda: self.reset_color(key))
            color_grid.addWidget(btn_reset, row, 3)

        add_color_row_grid(0, "You (Self):", 'Color_Self')
        add_color_row_grid(1, "Marked Cheater:", 'Color_Cheater')
        add_color_row_grid(2, "Marked Suspicious:", 'Color_Suspicious')
        add_color_row_grid(3, "Marked Other:", 'Color_Other')

        lay_app.addRow(color_grid)
        self.form_layout.addWidget(grp_app)

        action_layout = QHBoxLayout()
        action_layout.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Save Settings")
        btn_save.setDefault(True)
        btn_save.clicked.connect(self.save_all)
        action_layout.addWidget(btn_cancel)
        action_layout.addWidget(btn_save)
        main_layout.addLayout(action_layout)

        self.det_timer = QTimer(self)
        self.det_timer.timeout.connect(self.update_detection_label)
        self.det_timer.start(1000)
        self.update_detection_label()

    def toggle_echo(self, line_edit, btn):
        if line_edit.echoMode() == QLineEdit.Password:
            line_edit.setEchoMode(QLineEdit.Normal)
            btn.setText("Hide")
        else:
            line_edit.setEchoMode(QLineEdit.Password)
            btn.setText("Show")

    def redetect(self):
        self.logic.cached_detected_steamid = None
        self.logic.auto_detect_steamid()
        self.update_detection_label()

    def update_detection_label(self):
        val = self.logic.cached_detected_steamid
        if val:
            self.lbl_detected.setText(val)
            self.lbl_detected.setStyleSheet("color: green;")
        else:
            self.lbl_detected.setText("(Pending... Steam not running?)")
            self.lbl_detected.setStyleSheet("color: red;")

    def pick_color(self, key):
        curr = self.color_vars[key]
        c = QColorDialog.getColor(QColor(curr), self, "Select Color")
        if c.isValid():
            hex_c = c.name()
            self.color_vars[key] = hex_c
            self.color_widgets[key].setStyleSheet(f"background-color: {hex_c}; border: 1px solid black;")

    def reset_color(self, key):
        hex_c = DEFAULT_SETTINGS[key]
        self.color_vars[key] = hex_c
        self.color_widgets[key].setStyleSheet(f"background-color: {hex_c}; border: 1px solid black;")

    def save_all(self):
        for key, widget in self.vars.items():
            val = None
            if isinstance(widget, QLineEdit): val = widget.text()
            elif isinstance(widget, QCheckBox): val = str(widget.isChecked())
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)): val = str(widget.value())
            if val is not None: self.logic.set_setting(key, val)

        for key, val in self.color_vars.items():
            self.logic.set_setting(key, val)

        self.accept()
