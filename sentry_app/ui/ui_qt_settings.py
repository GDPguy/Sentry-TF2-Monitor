import os
import sys
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox,
                               QPushButton, QGroupBox, QScrollArea,
                               QWidget, QColorDialog, QFormLayout, QGridLayout,
                               QTableWidget, QTableWidgetItem, QHeaderView,
                               QAbstractItemView)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIntValidator, QColor

from ..consts import DEFAULT_SETTINGS

class SettingsWindow(QDialog):
    def __init__(self, parent, logic, px_func):
        super().__init__(parent)
        self.logic = logic
        self.px = px_func
        self.setWindowTitle("Settings")

        self.resize(self.px(720), self.px(850))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        checkbox_dim = self.px(18)
        font_size = self.px(10)
        self.checkbox_style = f"""
            QCheckBox::indicator {{ width: {checkbox_dim}px; height: {checkbox_dim}px; }}
            QCheckBox {{ font-size: {font_size}pt; }}
        """
        self.setStyleSheet(self.checkbox_style)

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

        self.vars['Auto_Update_TF2BD_Lists'] = QCheckBox("Auto-update enabled lists on startup")
        self.vars['Auto_Update_TF2BD_Lists'].setChecked(self.logic.get_setting_bool("Auto_Update_TF2BD_Lists"))
        lay_ext.addRow(self.vars['Auto_Update_TF2BD_Lists'])

        self.form_layout.addWidget(grp_ext)

        # ---- TF2BD Player Lists ----
        grp_lists = QGroupBox("TF2BD Player Lists")
        lay_lists = QVBoxLayout(grp_lists)
        lay_lists.setContentsMargins(8, 8, 8, 8)

        lbl_lists_help = QLabel(
            "Pick which cheater / suspicious-player lists to load. Built-in lists "
            "update automatically when the upstream repo changes; custom URLs are "
            "downloaded once and then refreshed via their embedded update_url.\n"
            "Files are saved under <code>tf2bd_lists/</code> next to Sentry.exe."
        )
        lbl_lists_help.setWordWrap(True)
        lbl_lists_help.setStyleSheet("color: gray;")
        lay_lists.addWidget(lbl_lists_help)

        # Table of lists: Name | Players | Enabled | Auto-update | Last Status | URL
        self.lists_table = QTableWidget(0, 6)
        self.lists_table.setHorizontalHeaderLabels(
            ['Name', 'Players', 'Enabled', 'Auto-Update', 'Last Status', 'URL']
        )
        self.lists_table.verticalHeader().setVisible(False)
        self.lists_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.lists_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.lists_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hdr = self.lists_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.Interactive)
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)
        self.lists_table.setColumnWidth(0, self.px(180))
        self.lists_table.setColumnWidth(4, self.px(220))
        self.lists_table.verticalHeader().setDefaultSectionSize(self.px(22))
        lay_lists.addWidget(self.lists_table)

        lists_btn_row = QHBoxLayout()
        self.btn_lists_add = QPushButton("Add Custom URL...")
        self.btn_lists_add.clicked.connect(self.lists_add_custom)
        self.btn_lists_remove = QPushButton("Remove Selected")
        self.btn_lists_remove.clicked.connect(self.lists_remove_selected)
        self.btn_lists_update = QPushButton("Update All Now")
        self.btn_lists_update.clicked.connect(self.lists_update_now)
        self.btn_lists_open = QPushButton("Open tf2bd_lists/ Folder")
        self.btn_lists_open.clicked.connect(self.lists_open_folder)
        lists_btn_row.addWidget(self.btn_lists_add)
        lists_btn_row.addWidget(self.btn_lists_remove)
        lists_btn_row.addWidget(self.btn_lists_update)
        lists_btn_row.addStretch()
        lists_btn_row.addWidget(self.btn_lists_open)
        lay_lists.addLayout(lists_btn_row)

        self.lists_status_label = QLabel("")
        self.lists_status_label.setWordWrap(True)
        self.lists_status_label.setStyleSheet("color: gray; font-style: italic;")
        lay_lists.addWidget(self.lists_status_label)

        self.form_layout.addWidget(grp_lists)

        # ---- end TF2BD Player Lists ----

        grp_auto = QGroupBox("Automation")
        lay_auto = QGridLayout(grp_auto)

        self.vars['Kick_Cheaters'] = QCheckBox("Auto Kick Cheaters")
        self.vars['Kick_Cheaters'].setChecked(self.logic.get_setting_bool('Kick_Cheaters'))
        lay_auto.addWidget(self.vars['Kick_Cheaters'], 0, 0)

        lbl_kick = QLabel("Attempts at most once every 170 seconds")

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

        lbl_cols = QLabel("Visible Columns (Main Window, Restart Required):")
        lay_app.addRow(lbl_cols)

        col_grid = QGridLayout()

        def add_col_cb(text, key, row, col):
            cb = QCheckBox(text)
            cb.setChecked(self.logic.get_setting_bool(key))
            self.vars[key] = cb
            col_grid.addWidget(cb, row, col)

        add_col_cb("Ping", 'Show_Ping_Column', 0, 0)
        add_col_cb("Kills", 'Show_Kills_Column', 0, 1)
        add_col_cb("Deaths", 'Show_Deaths_Column', 0, 2)
        add_col_cb("SteamID", 'Show_SteamID_Column', 0, 3)

        add_col_cb("Account Age", 'Show_Age_Column', 1, 0)
        add_col_cb("TF2 Hours", 'Show_Hours_Column', 1, 1)
        add_col_cb("VAC Bans", 'Show_VAC_Column', 1, 2)
        add_col_cb("Game Bans", 'Show_GameBans_Column', 1, 3)

        add_col_cb("SourceBans", 'Show_SB_Column', 2, 0)

        lay_app.addRow(col_grid)

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

        # Populate the TF2BD lists table with whatever's currently
        # configured, then wire up its checkbox toggles.
        self.refresh_lists_table()

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

    # ---- TF2BD lists table handlers ----

    def refresh_lists_table(self):
        """Re-render the lists table from ListManager.lists_config. Disables
        cell editing on the Name/URL/Players/Last Status columns and wires
        the Enabled/Auto-Update cells back to the manager on toggle."""
        from .ui_qt_dialogs import custom_askstring
        self._custom_askstring = custom_askstring  # keep ref alive

        # Avoid firing itemChanged during rebuild
        self.lists_table.blockSignals(True)
        try:
            self.lists_table.setRowCount(0)
            entries = self.logic.lists.get_lists()
            for entry in entries:
                row = self.lists_table.rowCount()
                self.lists_table.insertRow(row)

                # Name
                name_item = QTableWidgetItem(entry.get('name', ''))
                if entry.get('is_builtin'):
                    name_item.setData(Qt.UserRole, entry['url'])
                    suffix = '  (built-in)'
                    name_item.setText(entry.get('name', '') + suffix)
                    name_item.setForeground(Qt.gray)
                else:
                    name_item.setData(Qt.UserRole, entry['url'])
                self.lists_table.setItem(row, 0, name_item)

                # Players
                pc = entry.get('last_player_count', 0)
                pc_text = str(pc) if pc else '—'
                pc_item = QTableWidgetItem(pc_text)
                pc_item.setTextAlignment(Qt.AlignCenter)
                self.lists_table.setItem(row, 1, pc_item)

                # Enabled
                en_chk = QCheckBox()
                en_chk.setChecked(bool(entry.get('enabled', True)))
                en_chk.toggled.connect(
                    lambda checked, url=entry['url']: self._on_list_enabled_toggled(url, checked)
                )
                self.lists_table.setCellWidget(row, 2, en_chk)

                # Auto-update
                au_chk = QCheckBox()
                au_chk.setChecked(bool(entry.get('auto_update', True)))
                au_chk.toggled.connect(
                    lambda checked, url=entry['url']: self._on_list_autoupdate_toggled(url, checked)
                )
                self.lists_table.setCellWidget(row, 3, au_chk)

                # Last status
                status_item = QTableWidgetItem(entry.get('last_status', '') or '—')
                status_item.setToolTip(status_item.text())
                self.lists_table.setItem(row, 4, status_item)

                # URL
                url_item = QTableWidgetItem(entry.get('url', ''))
                url_item.setToolTip(entry.get('url', ''))
                self.lists_table.setItem(row, 5, url_item)
        finally:
            self.lists_table.blockSignals(False)

        # Show last update status as the group caption's helper text.
        last = self.logic.lists.last_update_status
        if last:
            self.lists_status_label.setText(f"Last update: {last}")
        else:
            self.lists_status_label.setText("")

    def _on_list_enabled_toggled(self, url, checked):
        self.logic.lists.set_list_enabled(url, checked)

    def _on_list_autoupdate_toggled(self, url, checked):
        self.logic.lists.set_list_auto_update(url, checked)

    def lists_add_custom(self):
        from .ui_qt_dialogs import custom_askstring
        url = custom_askstring(
            self, self.px,
            "Add Custom TF2BD List",
            "Paste the URL of a TF2BD-format JSON list:",
            "https://"
        )
        if not url:
            return
        url = url.strip()
        if not (url.startswith('http://') or url.startswith('https://')):
            from .ui_qt_dialogs import custom_popup
            custom_popup(self, self.px, "Invalid URL",
                         "URL must start with http:// or https://")
            return
        # Derive a default name from the URL basename
        from urllib.parse import urlparse
        path_basename = os.path.basename(urlparse(url).path.rstrip('/')) or 'custom'
        default_name = path_basename.replace('.json', '').replace('playerlist.', '')
        from .ui_qt_dialogs import custom_askstring
        name = custom_askstring(
            self, self.px,
            "List Name",
            "Display name for this list:",
            default_name.capitalize() + " List"
        )
        if not name:
            return

        ok = self.logic.lists.add_custom_list(name.strip(), url)
        if not ok:
            from .ui_qt_dialogs import custom_popup
            custom_popup(self, self.px, "Already Exists",
                         "A list with that URL is already configured.")
            return
        self.refresh_lists_table()

    def lists_remove_selected(self):
        row = self.lists_table.currentRow()
        if row < 0:
            return
        url = self.lists_table.item(row, 0).data(Qt.UserRole)
        entry = next((e for e in self.logic.lists.get_lists() if e.get('url') == url), None)
        if not entry:
            return
        if entry.get('is_builtin'):
            from .ui_qt_dialogs import custom_popup
            custom_popup(
                self, self.px, "Built-in List",
                "Built-in lists cannot be removed. Disable it instead "
                "(uncheck the Enabled column) and it won't be loaded."
            )
            return
        from .ui_qt_dialogs import custom_popup
        if custom_popup(
            self, self.px, "Remove List?",
            f"Remove '{entry.get('name')}' and delete its file from "
            "tf2bd_lists/?",
            is_confirmation=True,
        ):
            self.logic.lists.remove_list(url)
            self.refresh_lists_table()

    def lists_update_now(self):
        from .ui_qt_dialogs import custom_popup
        result = self.logic.lists.force_update_now()
        self.refresh_lists_table()
        custom_popup(
            self, self.px,
            "TF2BD List Update",
            result if result else "No changes."
        )

    def lists_open_folder(self):
        import subprocess
        # The tf2bd_lists/ directory sits at the working directory the
        # binary was launched from, which for a --onefile PyInstaller build
        # is the directory containing Sentry.exe. Resolve relative to that.
        exe_dir = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, 'frozen', False) \
            else os.getcwd()
        folder = os.path.join(exe_dir, 'tf2bd_lists')
        try:
            os.makedirs(folder, exist_ok=True)
            subprocess.Popen(['explorer', folder])
        except Exception as e:
            from .ui_qt_dialogs import custom_popup
            custom_popup(self, self.px, "Error",
                         f"Could not open folder:\n{e}")

    # ---- end TF2BD lists table handlers ----

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
