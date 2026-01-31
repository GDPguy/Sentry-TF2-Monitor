import webbrowser
import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGridLayout, QTextEdit,
    QWidget, QApplication, QToolTip, QRadioButton, QButtonGroup
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap, QCursor
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import QSizePolicy

from ..utils import convert_steamid3_to_steamid64


class PlayerDetailsWindow(QDialog):
    def __init__(self, parent, logic, player, px_func):
        super().__init__(parent)
        self.logic = logic
        self.player = player

        real_notes = self.logic.lists.get_user_notes(player.steamid)
        if real_notes is not None:
            self.player.notes = real_notes

        self.px = px_func
        self.parent_window = parent
        self.setWindowTitle(f"Player Details: {player.name}")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.nam = QNetworkAccessManager(self)
        self.s64 = convert_steamid3_to_steamid64(player.steamid)

        self.setup_ui()

    def closeEvent(self, event):
        try:
            if hasattr(self, 'avatar_reply') and self.avatar_reply:
                if self.avatar_reply.isRunning():
                    self.avatar_reply.abort()
                self.avatar_reply.deleteLater()
                self.avatar_reply = None
        except Exception:
            pass
        super().closeEvent(event)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Header: Avatar | Name + Stats
        header_layout = QHBoxLayout()
        header_layout.setSpacing(20)
        header_layout.setAlignment(Qt.AlignTop)

        self.lbl_avatar = QLabel()
        self.lbl_avatar.setFixedSize(self.px(100), self.px(100))
        self.lbl_avatar.setAlignment(Qt.AlignCenter)
        self.lbl_avatar.setText("Not fetched yet")
        header_layout.addWidget(self.lbl_avatar)

        if self.player.avatar_url:
            self.load_avatar(self.player.avatar_url)

        right_col_layout = QVBoxLayout()
        right_col_layout.setSpacing(5)
        right_col_layout.setAlignment(Qt.AlignTop)

        lbl_name = QLabel(self.player.name)
        lbl_name.setWordWrap(True)
        f_name = lbl_name.font()
        f_name.setBold(True)
        lbl_name.setFont(f_name)
        right_col_layout.addWidget(lbl_name)

        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(15)
        stats_grid.setVerticalSpacing(2)

        def add_stat(row, col, label, value, color=None, tooltip=None):
            l = QLabel(label)
            l.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            display_val = "Unknown" if value is None else str(value)

            v = QLabel(display_val)
            v.setStyleSheet("font-weight: bold;")
            if value is not None and color:
                v.setStyleSheet(f"font-weight: bold; color: {color};")
            if tooltip:
                v.setToolTip(tooltip)

            stats_grid.addWidget(l, row, col)
            stats_grid.addWidget(v, row, col + 1)

        def fmt_bool(val):
            if val is None:
                return None
            return "Yes" if val else "No"

        # Row 0: Age / Hours
        age_val = f"{self.player.account_age}y" if self.player.account_age is not None else None
        add_stat(0, 0, "Age:", age_val)

        mins = self.player.tf2_playtime
        hrs_val = f"{int(mins / 60)}h" if mins is not None else None
        add_stat(0, 2, "Hours:", hrs_val)

        # Row 1: VAC / Game bans
        vac_val = fmt_bool(self.player.vac_banned)
        vac_col = (
            "#ff4444" if self.player.vac_banned is True
            else ("#44cc44" if self.player.vac_banned is False else None)
        )
        add_stat(1, 0, "VAC:", vac_val, vac_col)

        if self.player.game_bans is None:
            gb_col = None
            gb_val = None
        else:
            gb_val = self.player.game_bans
            gb_col = "#ff4444" if self.player.game_bans > 0 else "#44cc44"
        add_stat(1, 2, "Game Bans:", gb_val, gb_col)

        # Row 2: SourceBans
        sb_count = self.player.ban_count
        if sb_count is None and self.player.sb_details is not None:
            relevant = [b for b in self.player.sb_details if b.get("CurrentState") != "Unbanned"]
            sb_count = len(relevant)

        sb_col = "#ff4444" if self.player.steamid in self.logic.get_suspicious_snapshot() else None
        add_stat(2, 0, "SourceBans:", sb_count, sb_col)

        # Row 3: Friends / Marked friends
        if self.player.friendlist_visible is False:
            friends_val = "Private"
        elif self.player.friend_count is None:
            friends_val = None
        else:
            friends_val = self.player.friend_count
        add_stat(3, 0, "Friends:", friends_val)

        mf = self.player.marked_friends_total
        if self.player.friendlist_visible is False:
            marked_val = "Private"
        elif mf is None:
            marked_val = None
        else:
            marked_val = mf

        marked_tooltip = None
        if self.player.friendlist_visible is True and getattr(self.player, "marked_cheater_friends_user", None) is not None:
            marked_tooltip = (
                f"Userlist - Cheater: {self.player.marked_cheater_friends_user}, "
                f"Suspicious: {self.player.marked_suspicious_friends_user}\n"
                f"TF2BD - Cheater: {self.player.marked_cheater_friends_tf2bd}, "
                f"Suspicious: {self.player.marked_suspicious_friends_tf2bd}"
            )

        marked_col = "#ff4444" if isinstance(mf, int) and mf > 0 else None
        add_stat(3, 2, "Marked Friends:", marked_val, marked_col, tooltip=marked_tooltip)

        right_col_layout.addLayout(stats_grid)
        header_layout.addLayout(right_col_layout, stretch=1)
        main_layout.addLayout(header_layout)

        # IDs
        ids_layout = QHBoxLayout()
        ids_layout.setSpacing(20)
        self.add_copy_label(ids_layout, f"ID3: {self.player.steamid}", self.player.steamid)
        if self.s64:
            self.add_copy_label(ids_layout, f"ID64: {self.s64}", str(self.s64))
        ids_layout.addStretch()
        main_layout.addLayout(ids_layout)

        # Links
        links_layout = QHBoxLayout()
        links_layout.setSpacing(10)

        def add_link(name, url_template):
            if not self.s64:
                return
            btn = QPushButton(name)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda: webbrowser.open(url_template.format(self.s64)))
            links_layout.addWidget(btn)

        add_link("Steam Profile", "https://steamcommunity.com/profiles/{}")
        add_link("SteamHistory", "https://steamhistory.net/id/{}")
        add_link("Rep.tf", "https://rep.tf/{}")
        add_link("RGL.gg", "https://rgl.gg/Public/PlayerProfile.aspx?p={}")
        add_link("Logs.tf", "https://logs.tf/profile/{}")
        links_layout.addStretch()
        main_layout.addLayout(links_layout)

        # TF2BD / SourceBans
        logs_layout = QHBoxLayout()
        logs_layout.setSpacing(10)

        # TF2BD
        tf2bd_widget = QWidget()
        tf2bd_layout = QVBoxLayout(tf2bd_widget)
        tf2bd_layout.setContentsMargins(5, 5, 5, 5)
        tf2bd_layout.setSpacing(4)

        lbl_tf2bd = QLabel("TF2BD Info")
        lbl_tf2bd.setStyleSheet("font-weight: bold;")
        tf2bd_layout.addWidget(lbl_tf2bd)

        tf2bd_text_raw = self.logic.lists.get_tf2bd_notes(self.player.steamid)
        if "No TF2BD data" in tf2bd_text_raw:
            tf2bd_text = "<i>No TF2 Bot Detector data found.</i>"
        else:
            tf2bd_text = tf2bd_text_raw.replace("\n", "<br>")

        self.txt_tf2bd = QTextEdit()
        self.txt_tf2bd.setReadOnly(True)
        self.txt_tf2bd.setHtml(tf2bd_text)
        tf2bd_layout.addWidget(self.txt_tf2bd)

        tf2bd_widget.setFixedHeight(self.px(150))
        logs_layout.addWidget(tf2bd_widget)

        # SourceBans
        sb_widget = QWidget()
        sb_layout = QVBoxLayout(sb_widget)
        sb_layout.setContentsMargins(5, 5, 5, 5)
        sb_layout.setSpacing(4)

        lbl_sb = QLabel("SourceBans Info")
        lbl_sb.setStyleSheet("font-weight: bold;")
        sb_layout.addWidget(lbl_sb)

        sb_details = self.player.sb_details
        if sb_details:
            sb_text = ""
            for b in sb_details:
                bd = datetime.datetime.fromtimestamp(b.get('BanTimestamp', 0)).strftime('%Y-%m-%d')
                sb_text += (
                    f"<b>{bd}</b> | {b.get('Server')}<br>"
                    f"Reason: {b.get('BanReason')}<br>"
                    f"State: {b.get('CurrentState')}<br>"
                    f"---<br>"
                )
        else:
            sb_text = "<i>No SourceBans history found.</i>"

        self.txt_sb = QTextEdit()
        self.txt_sb.setReadOnly(True)
        self.txt_sb.setHtml(sb_text)
        sb_layout.addWidget(self.txt_sb)

        sb_widget.setFixedHeight(self.px(150))
        logs_layout.addWidget(sb_widget)

        main_layout.addLayout(logs_layout)

        # User Entry editor
        user_widget = QWidget()
        ul_layout = QVBoxLayout(user_widget)
        ul_layout.setContentsMargins(5, 5, 5, 5)
        ul_layout.setSpacing(6)

        lbl_user = QLabel("User Entry")
        lbl_user.setStyleSheet("font-weight: bold;")
        ul_layout.addWidget(lbl_user)

        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText("Enter notes for this player...")
        self.txt_notes.setPlainText(self.player.notes or "")
        self.txt_notes.setFixedHeight(self.px(80))
        ul_layout.addWidget(self.txt_notes)

        controls_layout = QHBoxLayout()
        self.bg_mark = QButtonGroup(self)

        curr_type = self.logic.lists.get_user_mark(self.player.steamid)
        col_cheat = self.logic.get_setting_color('Color_Cheater')
        col_sus = self.logic.get_setting_color('Color_Suspicious')
        col_other = self.logic.get_setting_color('Color_Other')

        def add_radio(label, type_val, color_hex=None):
            rb = QRadioButton(label)
            if color_hex:
                rb.setStyleSheet(f"color: {color_hex}; font-weight: bold;")
            self.bg_mark.addButton(rb)
            if curr_type == type_val:
                rb.setChecked(True)
            return rb

        self.rb_cheat = add_radio("Cheater", "Cheater", col_cheat)
        self.rb_sus = add_radio("Suspicious", "Suspicious", col_sus)
        self.rb_other = add_radio("Other", "Other", col_other)

        if curr_type is None:
            self.rb_other.setChecked(True)

        controls_layout.addWidget(self.rb_cheat)
        controls_layout.addWidget(self.rb_sus)
        controls_layout.addWidget(self.rb_other)
        controls_layout.addStretch()

        btn_delete = QPushButton("Delete Entry")
        btn_delete.clicked.connect(self.delete_entry)

        btn_save = QPushButton("Save Entry")
        btn_save.clicked.connect(self.save_entry)


        controls_layout.addWidget(btn_delete)
        controls_layout.addWidget(btn_save)
        ul_layout.addLayout(controls_layout)

        foot = QHBoxLayout()
        foot.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        foot.addWidget(btn_close)
        ul_layout.addLayout(foot)

        sp = user_widget.sizePolicy()
        sp.setVerticalPolicy(QSizePolicy.Fixed)
        user_widget.setSizePolicy(sp)

        main_layout.addWidget(user_widget)

    def add_copy_label(self, layout, text, copy_val):
        lbl = QPushButton(text)
        lbl.setCursor(Qt.PointingHandCursor)
        lbl.setStyleSheet("text-align: left; border: none; background: transparent")
        lbl.clicked.connect(lambda: self.copy_to_clipboard(copy_val))
        layout.addWidget(lbl)

    def copy_to_clipboard(self, text):
        QApplication.clipboard().setText(text)
        QToolTip.showText(QCursor.pos(), "Copied!", self)

    def load_avatar(self, url):
        req = QNetworkRequest(QUrl(url))
        self.avatar_reply = self.nam.get(req)
        self.avatar_reply.finished.connect(self.on_avatar_loaded)

    def on_avatar_loaded(self):
        reply = self.sender()
        if not reply:
            return

        if not self.isVisible():
            reply.deleteLater()
            self.avatar_reply = None
            return

        if reply.error() == QNetworkReply.NoError:
            data = reply.readAll()
            pix = QPixmap()
            if pix.loadFromData(data):
                self.lbl_avatar.setPixmap(
                    pix.scaled(self.lbl_avatar.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                self.lbl_avatar.setText("")

        reply.deleteLater()
        self.avatar_reply = None

    def save_entry(self):
        txt = self.txt_notes.toPlainText()
        ptype = "Other"
        if self.rb_cheat.isChecked():
            ptype = "Cheater"
        elif self.rb_sus.isChecked():
            ptype = "Suspicious"

        self.logic.mark_player(self.player.steamid, ptype, name=self.player.name, notes=txt)

        if hasattr(self.parent_window, 'apply_local_update'):
            self.parent_window.apply_local_update(self.player.steamid, ptype=ptype, note=txt)

    def delete_entry(self):
        if self.parent_window.actions.delete(self.player.steamid, self.player.name):
            self.txt_notes.clear()
            self.rb_other.setChecked(True)
            if hasattr(self.parent_window, 'apply_local_update'):
                self.parent_window.apply_local_update(self.player.steamid, ptype="CLEAR", note="")
