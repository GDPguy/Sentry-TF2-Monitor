import os
import threading
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QVBoxLayout,
    QWidget,
)

from ..utils import restart_application


COL_NAME = 0
COL_PLAYERS = 1
COL_ENABLED = 2
COL_UPDATES_ENABLED = 3
COL_STATUS = 4
COL_URL = 5
COL_FILENAME = 6


class ListEditDelegate(QStyledItemDelegate):

    def __init__(self, parent, name_limit):
        super().__init__(parent)
        self.name_limit = name_limit

    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit) and index.column() == COL_NAME:
            editor.setMaxLength(self.name_limit)
        return editor


class TF2BDListManagerWindow(QDialog):
    update_finished = Signal(str)

    def __init__(self, parent, logic, px_func):
        super().__init__(parent)
        self.logic = logic
        self.px = px_func
        self._update_running = False
        self._finishing = False
        self._successful_manual_updates = 0
        self._startup_waiting = self.logic.lists.is_startup_update_running()



        discovered_local_lists = 0
        if not self._startup_waiting:
            discovered_local_lists = self.logic.lists.refresh_lists_from_disk()

        self.setWindowTitle("TF2BD List Manager")
        self.resize(self.px(1120), self.px(540))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)

        auto_row = QHBoxLayout()
        self.chk_auto_updates = QCheckBox("Auto update player lists on startup")
        self.chk_auto_updates.setChecked(
            self.logic.get_setting_bool("Auto_Update_TF2BD_Lists")
        )
        self.chk_auto_updates.setToolTip(
            "Disable to prevent lists from being updated on startup."
        )
        self.chk_auto_updates.toggled.connect(self._on_auto_updates_toggled)
        auto_row.addWidget(self.chk_auto_updates)
        auto_row.addStretch()
        layout.addLayout(auto_row)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "Name",
                "Players",
                "Enabled",
                "Updates Enabled",
                "Last Status",
                "Update URL",
                "Filename",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self.table.verticalHeader().setDefaultSectionSize(self.px(24))
        self.table.setItemDelegate(
            ListEditDelegate(
                self.table,
                self.logic.lists.LIST_NAME_MAX_LENGTH,
            )
        )

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_NAME, QHeaderView.Interactive)
        header.setSectionResizeMode(COL_PLAYERS, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_ENABLED, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_UPDATES_ENABLED, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.Interactive)
        header.setSectionResizeMode(COL_URL, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_FILENAME, QHeaderView.Interactive)

        self.table.setColumnWidth(COL_NAME, self.px(190))
        self.table.setColumnWidth(COL_STATUS, self.px(220))
        self.table.setColumnWidth(COL_FILENAME, self.px(190))
        self.table.itemChanged.connect(self._on_item_changed)


        self.table.horizontalHeaderItem(COL_ENABLED).setToolTip(
            "Controls whether this list's player data is loaded after Sentry restarts. "
            "Disabled lists are also excluded from update checks."
        )
        self.table.horizontalHeaderItem(COL_UPDATES_ENABLED).setToolTip(
            "Controls whether this enabled list is included in automatic and manual update checks. "
            "Disabled lists are never updated."
        )
        self.table.horizontalHeaderItem(COL_URL).setToolTip(
            "Source used to update or restore this list. Local-only lists have no Update URL."
        )
        layout.addWidget(self.table)

        button_row = QHBoxLayout()

        self.btn_add = QPushButton("Add Custom URL...")
        self.btn_add.clicked.connect(self.add_custom_list)
        button_row.addWidget(self.btn_add)

        self.btn_remove = QPushButton("Remove Selected")
        self.btn_remove.clicked.connect(self.remove_selected)
        button_row.addWidget(self.btn_remove)

        self.btn_update_selected = QPushButton("Force Update Selected List")
        self.btn_update_selected.setToolTip(
            "Update the selected list from its Update URL, ignoring Enabled and Updates Enabled."
        )
        self.btn_update_selected.clicked.connect(self.update_selected_now)
        button_row.addWidget(self.btn_update_selected)

        self.btn_update = QPushButton("Update Lists Now")
        self.btn_update.setToolTip(
            "Check for updates for lists where both Enabled and Updates Enabled are checked."
        )
        self.btn_update.clicked.connect(self.update_all_now)
        button_row.addWidget(self.btn_update)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setToolTip("Scan the tf2bd_lists/ folder for changes.")
        self.btn_refresh.clicked.connect(self.refresh_from_disk)
        button_row.addWidget(self.btn_refresh)

        button_row.addStretch()

        self.btn_open = QPushButton("Open tf2bd_lists/ Folder")
        self.btn_open.clicked.connect(self.open_folder)
        button_row.addWidget(self.btn_open)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        button_row.addWidget(self.btn_close)

        layout.addLayout(button_row)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.update_finished.connect(self._on_update_finished)

        self._startup_watch_timer = QTimer(self)
        self._startup_watch_timer.setInterval(150)
        self._startup_watch_timer.timeout.connect(self._check_startup_update)

        if self._startup_waiting:


            self._set_startup_waiting_controls(True)
            self._set_status("Startup list update in progress...")
            self._startup_watch_timer.start()
        else:
            self.refresh_table()
            if discovered_local_lists:
                suffix = "list" if discovered_local_lists == 1 else "lists"
                self._set_status(f"Found {discovered_local_lists} new local {suffix}.")

    def _set_status(self, text, *, error=False, tooltip=None):
        self.status_label.setText(text)
        self.status_label.setToolTip(tooltip or "")
        if error:
            self.status_label.setStyleSheet("color: red;")
        else:
            self.status_label.setStyleSheet("")

    def _readonly_item(self, text):
        item = QTableWidgetItem(str(text))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _editable_item(self, text, filename):
        item = QTableWidgetItem(str(text))
        item.setData(Qt.UserRole, filename)
        return item

    def _checkbox_widget(self, checked, callback, *, enabled=True, tooltip=""):
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setAlignment(Qt.AlignCenter)

        checkbox = QCheckBox()
        checkbox.setChecked(bool(checked))
        checkbox.setEnabled(enabled)
        if tooltip:
            checkbox.setToolTip(tooltip)
            holder.setToolTip(tooltip)
        checkbox.toggled.connect(callback)
        row.addWidget(checkbox)
        return holder

    def refresh_table(self):
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            for entry in self.logic.lists.get_lists():
                row = self.table.rowCount()
                self.table.insertRow(row)

                filename = entry.get("filename", "")

                name_item = self._editable_item(entry.get("name", ""), filename)
                name_item.setToolTip(
                    f"Double-click to edit the local display name "
                    f"(max {self.logic.lists.LIST_NAME_MAX_LENGTH} characters)."
                )
                self.table.setItem(row, COL_NAME, name_item)

                player_count = entry.get("last_player_count", 0)
                players_item = self._readonly_item(
                    str(player_count) if player_count else "—"
                )
                players_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, COL_PLAYERS, players_item)

                enabled_widget = self._checkbox_widget(
                    entry.get("enabled", True),
                    lambda checked, fn=filename: self._on_enabled_toggled(fn, checked),
                    tooltip=(
                        "Load this list's player data the next time Sentry starts. "
                        "Disabled lists are also excluded from update checks."
                    ),
                )
                self.table.setCellWidget(row, COL_ENABLED, enabled_widget)

                has_url = bool(entry.get("url"))
                list_enabled = bool(entry.get("enabled", True))
                updates_control_enabled = has_url and list_enabled
                if not has_url:
                    updates_tooltip = (
                        "Local-only lists cannot be updated because they have no Update URL."
                    )
                elif not list_enabled:
                    updates_tooltip = (
                        "Disabled lists are not updated. Enable this list to change its update setting."
                    )
                else:
                    updates_tooltip = (
                        "Toggle whether this enabled list is included in automatic and manual update checks."
                    )

                auto_widget = self._checkbox_widget(
                    entry.get("auto_update", has_url),
                    lambda checked, fn=filename: self._on_auto_update_toggled(fn, checked),
                    enabled=updates_control_enabled,
                    tooltip=updates_tooltip,
                )
                self.table.setCellWidget(row, COL_UPDATES_ENABLED, auto_widget)

                status_text = entry.get("last_status", "") or "—"
                status_item = self._readonly_item(status_text)
                status_item.setToolTip(status_text)
                status_lower = status_text.lower()
                if (
                    "failed" in status_lower
                    or "error" in status_lower
                    or status_lower == "file missing"
                ):
                    status_item.setForeground(QColor("red"))
                self.table.setItem(row, COL_STATUS, status_item)

                url = entry.get("url", "")
                url_item = self._readonly_item(url)
                url_item.setToolTip(
                    "Source used to update or restore this list. "
                    "The URL is supplied by the TF2BD list metadata."
                    if url else
                    "This is a local-only list; its TF2BD metadata does not provide an Update URL."
                )
                self.table.setItem(row, COL_URL, url_item)

                filename_item = self._readonly_item(filename)
                self.table.setItem(row, COL_FILENAME, filename_item)
        finally:
            self.table.blockSignals(False)

    def _find_entry(self, filename):
        return next(
            (
                entry for entry in self.logic.lists.get_lists()
                if entry.get("filename") == filename
            ),
            None,
        )

    def _on_item_changed(self, item):
        if item.column() != COL_NAME:
            return

        filename = item.data(Qt.UserRole)
        if not filename:
            return

        new_name = item.text().strip()
        if self.logic.lists.set_list_name(filename, new_name):
            if item.text() != new_name:
                self.table.blockSignals(True)
                item.setText(new_name)
                self.table.blockSignals(False)
            self._set_status("Display name saved.")
            return

        entry = self._find_entry(filename)
        old_name = entry.get("name", filename) if entry else filename
        self.table.blockSignals(True)
        item.setText(old_name)
        self.table.blockSignals(False)
        self._set_status(
            f"Display name must be 1-{self.logic.lists.LIST_NAME_MAX_LENGTH} characters.",
            error=True,
        )

    def _on_auto_updates_toggled(self, checked):
        self.logic.set_setting("Auto_Update_TF2BD_Lists", str(checked))
        self._set_status(
            "Automatic startup updates enabled."
            if checked else "Automatic startup updates disabled."
        )

    def _on_enabled_toggled(self, filename, checked):
        if self.logic.lists.set_list_enabled(filename, checked):
            self.refresh_table()
            self._set_status("Enabled List." if checked else "Disabled List.")

    def _on_auto_update_toggled(self, filename, checked):
        if self.logic.lists.set_list_auto_update(filename, checked):


            self.refresh_table()
            self._set_status(
                "Updates enabled for this list."
                if checked else "Updates disabled for this list."
            )

    def _prompt_for_available_filename(self, desired):
        from .ui_qt_dialogs import custom_askstring, custom_popup

        current = desired
        while self.logic.lists.filename_in_use(current):
            suggested = self.logic.lists.next_available_filename(current)
            entered = custom_askstring(
                self,
                self.px,
                "Filename Already Exists",
                f"'{current}' already exists in tf2bd_lists/.\n"
                "Choose a different filename for this list:",
                suggested,
            )
            if entered is None:
                return None
            normalized = self.logic.lists.normalize_custom_filename(entered)
            if not normalized:
                custom_popup(
                    self,
                    self.px,
                    "Invalid Filename",
                    "Enter a plain JSON filename without folders or characters such as < > : \" | ? *.",
                )
                current = suggested
                continue
            current = normalized
        return self.logic.lists.normalize_custom_filename(current)

    def add_custom_list(self):
        from .ui_qt_dialogs import custom_askstring, custom_popup

        url = custom_askstring(
            self,
            self.px,
            "Add Custom TF2BD List",
            "Paste the URL of a TF2BD-format JSON list:",
            "https://",
        )
        if not url:
            return

        url = url.strip()
        if len(url) > self.logic.lists.LIST_URL_MAX_LENGTH:
            custom_popup(
                self,
                self.px,
                "URL Too Long",
                f"URLs are limited to {self.logic.lists.LIST_URL_MAX_LENGTH} characters.",
            )
            return
        if not url.startswith(("http://", "https://")):
            custom_popup(
                self,
                self.px,
                "Invalid URL",
                "URL must start with http:// or https://",
            )
            return

        matches = [e for e in self.logic.lists.get_lists() if e.get("url") == url]
        if matches:
            if len(matches) == 1:
                existing = matches[0]
                message = (
                    "That Update URL is already configured for "
                    f"'{existing.get('name', existing.get('filename', 'this list'))}'."
                )
            else:
                message = (
                    f"That Update URL is already configured for {len(matches)} lists."
                )
            custom_popup(
                self,
                self.px,
                "List Already Present",
                message,
            )
            return

        path_basename = os.path.basename(urlparse(url).path.rstrip("/")) or "custom"
        default_name = path_basename.replace(".json", "").replace("playerlist.", "")
        default_name = (
            default_name.capitalize() + " List"
        )[:self.logic.lists.LIST_NAME_MAX_LENGTH]
        name = custom_askstring(
            self,
            self.px,
            "List Name",
            "Display name for this list:",
            default_name,
        )
        if not name:
            return

        name = name.strip()
        if not name or len(name) > self.logic.lists.LIST_NAME_MAX_LENGTH:
            custom_popup(
                self,
                self.px,
                "Invalid List Name",
                f"List names must be 1-{self.logic.lists.LIST_NAME_MAX_LENGTH} characters.",
            )
            return

        desired_filename = self.logic.lists.suggested_filename(name, url)
        filename = self._prompt_for_available_filename(desired_filename)
        if not filename:
            return

        self._set_status("Importing list...")
        if not self.logic.lists.add_custom_list(name, url, filename=filename):
            custom_popup(
                self,
                self.px,
                "Could Not Import List",
                self.logic.lists.last_add_error or "The list could not be imported.",
            )
            self._set_status("List import failed. Nothing was saved.", error=True)
            return

        self.refresh_table()
        self._set_status("List imported.")

    def remove_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return

        name_item = self.table.item(row, COL_NAME)
        if not name_item:
            return

        filename = name_item.data(Qt.UserRole)
        entry = self._find_entry(filename)
        if not entry:
            return

        from .ui_qt_dialogs import custom_popup
        if not custom_popup(
            self,
            self.px,
            "Remove List?",
            f"Remove '{entry.get('name')}' and delete its file from tf2bd_lists/?",
            is_confirmation=True,
        ):
            return

        if self.logic.lists.remove_list(filename):
            self.refresh_table()
            self._set_status("List removed.")

    def refresh_from_disk(self):
        added = self.logic.lists.refresh_lists_from_disk()
        self.refresh_table()
        if added:
            suffix = "list" if added == 1 else "lists"
            self._set_status(f"Found {added} new local {suffix}.")
        else:
            self._set_status("List folder refreshed.")

    def _set_update_controls_enabled(self, enabled):
        self.table.setEnabled(enabled)
        self.chk_auto_updates.setEnabled(enabled)
        self.btn_add.setEnabled(enabled)
        self.btn_remove.setEnabled(enabled)
        self.btn_update_selected.setEnabled(enabled)
        self.btn_update.setEnabled(enabled)
        self.btn_refresh.setEnabled(enabled)
        self.btn_open.setEnabled(enabled)
        self.btn_close.setEnabled(enabled)

    def _set_startup_waiting_controls(self, waiting):
        enabled = not waiting
        self.table.setEnabled(enabled)
        self.chk_auto_updates.setEnabled(enabled)
        self.btn_add.setEnabled(enabled)
        self.btn_remove.setEnabled(enabled)
        self.btn_update_selected.setEnabled(enabled)
        self.btn_update.setEnabled(enabled)
        self.btn_refresh.setEnabled(enabled)
        self.btn_open.setEnabled(True)
        self.btn_close.setEnabled(True)

    def _check_startup_update(self):
        if self.logic.lists.is_startup_update_running():
            return

        self._startup_watch_timer.stop()
        self._startup_waiting = False



        discovered_local_lists = self.logic.lists.refresh_lists_from_disk()
        self.refresh_table()
        self._set_startup_waiting_controls(False)

        result = self.logic.lists.last_update_status or ""
        lowered = result.lower()
        has_error = "error" in lowered or "failed" in lowered

        if discovered_local_lists:
            suffix = "list" if discovered_local_lists == 1 else "lists"
            self._set_status(
                f"Found {discovered_local_lists} new local {suffix}.",
                error=has_error,
                tooltip=result or None,
            )
        elif has_error:
            self._set_status(
                "Startup list update completed with errors.",
                error=True,
                tooltip=result,
            )
        else:
            self._set_status("Startup list update complete.", tooltip=result or None)

    def update_selected_now(self):
        if self._update_running:
            return

        row = self.table.currentRow()
        if row < 0:
            self._set_status("Select a list to update.")
            return

        name_item = self.table.item(row, COL_NAME)
        if not name_item:
            self._set_status("Select a list to update.")
            return

        filename = name_item.data(Qt.UserRole)
        entry = self._find_entry(filename)
        if not entry:
            self._set_status("Selected list could not be found.", error=True)
            return
        if not entry.get("url"):
            self._set_status("List does not have an update URL.")
            return
        self._update_running = True
        self._update_scope = "selected"
        self._set_update_controls_enabled(False)
        self._set_status("Updating selected list...")

        def worker():
            try:
                result = self.logic.lists.force_update_list(filename)
            except Exception as exc:
                result = f"Error: {exc}"
            self.update_finished.emit(result or "")

        threading.Thread(target=worker, daemon=True).start()

    def update_all_now(self):
        if self._update_running:
            return

        self._update_running = True
        self._update_scope = "all"
        self._set_update_controls_enabled(False)
        self._set_status("Updating...")

        def worker():
            try:
                result = self.logic.lists.force_update_now()
            except Exception as exc:
                result = f"Error: {exc}"
            self.update_finished.emit(result or "")

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_finished(self, result):
        self._update_running = False
        self._set_update_controls_enabled(True)
        self.refresh_table()

        changed_count = self.logic.lists.last_update_changed_count
        scope = getattr(self, "_update_scope", "all")

        if changed_count:
            self._successful_manual_updates += changed_count

        lowered = result.lower()
        has_error = "error" in lowered or "failed" in lowered

        if has_error:
            text = "Update failed." if scope == "selected" else "Update completed with errors."
            self._set_status(text, error=True, tooltip=result)
        elif changed_count:
            self._set_status("Update complete.", tooltip=result)
        else:
            if scope == "selected":
                self._set_status("Selected list is already up to date.", tooltip=result)
            elif "No lists selected for updates." in result:
                self._set_status("No enabled lists are selected for updates.", tooltip=result)
            else:
                self._set_status("Selected lists are already up to date.", tooltip=result)

    def open_folder(self):
        from .ui_qt_dialogs import custom_popup

        folder = os.path.abspath(self.logic.lists.tf2bd_dir)
        try:
            os.makedirs(folder, exist_ok=True)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(folder)):
                raise RuntimeError("The operating system could not open the folder.")
        except Exception as exc:
            custom_popup(
                self,
                self.px,
                "Error",
                f"Could not open folder:\n{exc}",
            )

    def done(self, result):
        if self._update_running:
            self._set_status("Please wait for the list update to finish.")
            return




        if self.logic.lists.is_startup_update_running():
            super().done(result)
            return

        if self._finishing:
            super().done(result)
            return

        self._finishing = True
        restart_now = False

        if self.logic.lists.should_prompt_tf2bd_restart():
            from .ui_qt_dialogs import custom_popup
            count = self._successful_manual_updates
            if count:
                noun = "list" if count == 1 else "lists"
                message = (
                    f"{count} {noun} successfully updated. "
                    "Updated list data will be active once Sentry restarts.\n\n"
                    "Restart now?"
                )
            else:
                message = (
                    "TF2BD list changes will be active once Sentry restarts.\n\n"
                    "Restart now?"
                )
            restart_now = custom_popup(
                self,
                self.px,
                "Restart Sentry?",
                message,
                is_confirmation=True,
            )
            if not restart_now:
                self.logic.lists.suppress_tf2bd_restart_prompt()

        super().done(result)

        if restart_now:
            QTimer.singleShot(0, self._restart_sentry)

    def _restart_sentry(self):
        if restart_application():
            return

        from .ui_qt_dialogs import custom_popup
        parent = self.parentWidget()
        custom_popup(
            parent,
            self.px,
            "Restart Failed",
            "Sentry could not start a replacement process. Your changes are saved "
            "and will apply the next time you start Sentry.",
        )
