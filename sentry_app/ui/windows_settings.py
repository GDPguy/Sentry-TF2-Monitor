import tkinter as tk
from tkinter import ttk, colorchooser
import tkinter.font as tkfont
from .widgets import ScrollableFrame
from ..consts import DEFAULT_SETTINGS

class SettingsWindow:
    def __init__(self, root, logic_manager, px_func, on_close_callback=None):
        self.root = root
        self.logic = logic_manager
        self.window = tk.Toplevel(root)
        self.window.title("Settings")
        self.px = px_func

        self.window.transient(root)
        self.window.grab_set()
        self.window.focus_set()

        self.window.geometry(f"{self.px(720)}x{self.px(800)}")
        self.window.resizable(True, True)

        # Input Validation Wrappers
        def validate_number(P):
            if P == "": return True
            return P.isdigit() and len(P) <= 5
        def validate_length_short(P):
            return len(P) <= 32
        def validate_length_medium(P):
            return len(P) <= 64
        def validate_length_long(P):
            return len(P) <= 128

        vcmd_num = (self.window.register(validate_number), '%P')
        vcmd_short = (self.window.register(validate_length_short), '%P')
        vcmd_med = (self.window.register(validate_length_medium), '%P')
        vcmd_long = (self.window.register(validate_length_long), '%P')

        # Main Layout
        self.window.grid_rowconfigure(0, weight=1)
        self.window.grid_columnconfigure(0, weight=1)

        scroll = ScrollableFrame(self.window, scroll_x=False, scroll_y=True, fit_width=True)
        scroll.grid(row=0, column=0, sticky="nsew")

        parent = scroll.content
        parent.grid_columnconfigure(0, weight=1)

        # Fonts
        default_font = tkfont.nametofont("TkDefaultFont")
        bold_font = default_font.copy()
        bold_font.configure(weight="bold")
        hint_font = default_font.copy()
        hint_font.configure(size=max(7, int(default_font.cget("size") * 0.85)), slant="italic")
        bold_hint_font = default_font.copy()
        bold_hint_font.configure(size=max(7, int(default_font.cget("size") * 0.85)), slant="italic", weight="bold")

        # --- Load Variables ---
        s_user_var = tk.StringVar(value=self.logic.get_setting('User'))
        s_use_manual_steamid_bool = tk.BooleanVar(value=self.logic.get_setting_bool('Use_Manual_SteamID'))

        s_rcon_pass_var = tk.StringVar(value=self.logic.get_setting('RCon_Password'))
        s_rcon_port_var = tk.StringVar(value=self.logic.get_setting('RCon_Port'))
        s_api_key_var = tk.StringVar(value=self.logic.get_setting('SteamHistory_API_Key'))

        s_kick_bool = tk.BooleanVar(value=self.logic.get_setting_bool('Kick_Cheaters'))
        s_kick_int = tk.IntVar(value=self.logic.get_setting_int('Kick_Cheaters_Interval'))

        s_announce_bool = tk.BooleanVar(value=self.logic.get_setting_bool('Announce_Cheaters'))
        s_announce_int = tk.IntVar(value=self.logic.get_setting_int('Announce_Cheaters_Interval'))

        s_party_cheat_bool = tk.BooleanVar(value=self.logic.get_setting_bool('Party_Announce_Cheaters'))
        s_party_ban_bool = tk.BooleanVar(value=self.logic.get_setting_bool('Party_Announce_Bans'))

        s_ui_scale = tk.DoubleVar(value=self.logic.get_setting_float('UI_Scale'))

        s_auto_update_tf2bd = tk.BooleanVar(value=self.logic.get_setting_bool("Auto_Update_TF2BD_Lists"))
        s_enable_sourcebans = tk.BooleanVar(value=self.logic.get_setting_bool("Enable_Sourcebans_Lookup"))

        # Color Vars
        s_col_self = tk.StringVar(value=self.logic.get_setting_color('Color_Self'))
        s_col_cheater = tk.StringVar(value=self.logic.get_setting_color('Color_Cheater'))
        s_col_sus = tk.StringVar(value=self.logic.get_setting_color('Color_Suspicious'))
        s_col_other = tk.StringVar(value=self.logic.get_setting_color('Color_Other'))

        s_save_names = tk.BooleanVar(value=self.logic.get_setting_bool('Save_Player_Names'))
        s_save_times = tk.BooleanVar(value=self.logic.get_setting_bool('Save_Player_Timestamps'))

        def save_and_close():
            self.logic.set_setting('User', s_user_var.get())
            self.logic.set_setting('Use_Manual_SteamID', str(s_use_manual_steamid_bool.get()))
            self.logic.set_setting('RCon_Password', s_rcon_pass_var.get())
            self.logic.set_setting('RCon_Port', s_rcon_port_var.get())
            self.logic.set_setting('SteamHistory_API_Key', s_api_key_var.get())

            new_scale = f"{s_ui_scale.get():.2f}"
            self.logic.set_setting('UI_Scale', new_scale)

            self.logic.set_setting('Kick_Cheaters', str(s_kick_bool.get()))
            self.logic.set_setting('Kick_Cheaters_Interval', str(s_kick_int.get()))
            self.logic.set_setting('Announce_Cheaters', str(s_announce_bool.get()))
            self.logic.set_setting('Announce_Cheaters_Interval', str(s_announce_int.get()))
            self.logic.set_setting('Party_Announce_Cheaters', str(s_party_cheat_bool.get()))
            self.logic.set_setting('Party_Announce_Bans', str(s_party_ban_bool.get()))
            self.logic.set_setting("Auto_Update_TF2BD_Lists", str(s_auto_update_tf2bd.get()))
            self.logic.set_setting("Enable_Sourcebans_Lookup", str(s_enable_sourcebans.get()))

            self.logic.set_setting('Color_Self', s_col_self.get())
            self.logic.set_setting('Color_Cheater', s_col_cheater.get())
            self.logic.set_setting('Color_Suspicious', s_col_sus.get())
            self.logic.set_setting('Color_Other', s_col_other.get())

            self.logic.set_setting('Save_Player_Names', str(s_save_names.get()))
            self.logic.set_setting('Save_Player_Timestamps', str(s_save_times.get()))

            self.window.destroy()

        def create_section(title, row_idx):
            lf = ttk.LabelFrame(parent, text=f" {title} ", padding=(10, 10))
            lf.grid(row=row_idx, column=0, sticky="ew", padx=10, pady=5)
            lf.grid_columnconfigure(1, weight=1)
            return lf

        # ==========================================
        # SECTION 1: CONNECTION & IDENTITY
        # ==========================================
        frame_conn = create_section("Connection & Identity", 0)

        ttk.Label(frame_conn, text="RCon Password:").grid(row=0, column=0, sticky="w", pady=5)
        rcon_container = ttk.Frame(frame_conn)
        rcon_container.grid(row=0, column=1, sticky="ew", padx=10)
        rcon_entry = ttk.Entry(rcon_container, textvariable=s_rcon_pass_var, show="*", validate="key", validatecommand=vcmd_long)
        rcon_entry.pack(side="left", fill="x", expand=True)
        def toggle_rcon():
            rcon_entry.config(show='' if rcon_entry.cget('show') == '*' else '*')
        ttk.Button(rcon_container, text="Toggle", width=6, command=toggle_rcon).pack(side="left", padx=(5, 0))

        ttk.Label(frame_conn, text="RCon Port:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(frame_conn, textvariable=s_rcon_port_var, width=10, validate="key", validatecommand=vcmd_num).grid(row=1, column=1, sticky="w", padx=10)

        ttk.Separator(frame_conn, orient="horizontal").grid(row=2, column=0, columnspan=2, sticky="ew", pady=10)

        detect_row = ttk.Frame(frame_conn)
        detect_row.grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 5))
        lbl_detected_title = ttk.Label(detect_row, text="Auto-Detected:")
        lbl_detected_title.pack(side="left", padx=(0, 5))
        lbl_detected_val = ttk.Label(detect_row, text="...", font=hint_font)
        lbl_detected_val.pack(side="left")

        def manual_redetect():
            self.logic.cached_detected_steamid = None
            self.logic.auto_detect_steamid()
            update_detected_label()
        ttk.Button(detect_row, text="Redetect", width=8, command=manual_redetect).pack(side="left", padx=(10, 0))

        fallback_row = ttk.Frame(frame_conn)
        fallback_row.grid(row=4, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Label(fallback_row, text="Fallback SteamID3:").pack(side="left")
        ttk.Entry(fallback_row, textvariable=s_user_var, width=20, validate="key", validatecommand=vcmd_short).pack(side="left", padx=(5, 0))

        ttk.Checkbutton(frame_conn, text="Always use this ID (Override auto-detection)", variable=s_use_manual_steamid_bool).grid(row=5, column=0, columnspan=2, sticky="w", padx=0, pady=2)
        ttk.Label(frame_conn, text="SteamID3 is used to highlight your name in the player list.", font=hint_font).grid(row=6, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 5))

        def update_detected_label():
            if not self.window.winfo_exists(): return
            val = self.logic.cached_detected_steamid
            if val: lbl_detected_val.config(text=val, foreground="#44cc44")
            else: lbl_detected_val.config(text="(Pending... Steam not running?)", foreground="#ff5555")
            self.window.after(1000, update_detected_label)
        update_detected_label()

        # ==========================================
        # SECTION 2: INTERNET & API
        # ==========================================
        frame_ext = create_section("Internet & API", 1)
        ttk.Label(frame_ext, text="SteamHistory API Key:").grid(row=0, column=0, sticky="w", pady=5)
        api_container = ttk.Frame(frame_ext)
        api_container.grid(row=0, column=1, sticky="ew", padx=10)
        api_entry = ttk.Entry(api_container, textvariable=s_api_key_var, show="*", validate="key", validatecommand=vcmd_med)
        api_entry.pack(side="left", fill="x", expand=True)
        def toggle_api():
            api_entry.config(show='' if api_entry.cget('show') == '*' else '*')
        ttk.Button(api_container, text="Toggle", width=6, command=toggle_api).pack(side="left", padx=(5, 0))

        ttk.Checkbutton(frame_ext, text="Enable SteamHistory SourceBans Lookup", variable=s_enable_sourcebans).grid(row=1, column=1, sticky="w", padx=10, pady=(5, 0))
        ttk.Checkbutton(frame_ext, text="Auto-update TF2BD lists on startup", variable=s_auto_update_tf2bd).grid(row=2, column=1, sticky="w", padx=10, pady=(2, 5))

        # ==========================================
        # SECTION 3: AUTOMATION
        # ==========================================
        frame_auto = create_section("Automation", 2)
        frame_auto.columnconfigure(2, weight=1)

        ttk.Checkbutton(frame_auto, text="Auto Kick Cheaters", variable=s_kick_bool).grid(row=0, column=0, sticky="w")
        lbl_kick_val = ttk.Label(frame_auto, text=f"Interval: {s_kick_int.get()}s", font=hint_font)
        lbl_kick_val.grid(row=0, column=1, sticky="e", padx=(10, 5))
        def update_kick_lbl(val):
            s_kick_int.set(int(float(val)))
            lbl_kick_val.config(text=f"Interval: {int(float(val))}s")
        ttk.Scale(frame_auto, from_=5, to=60, orient='horizontal', variable=s_kick_int, command=update_kick_lbl, length=self.px(120)).grid(row=0, column=2, sticky="w")

        ttk.Checkbutton(frame_auto, text="Global Chat Announce", variable=s_announce_bool).grid(row=1, column=0, sticky="w")
        lbl_ann_val = ttk.Label(frame_auto, text=f"Interval: {s_announce_int.get()}s", font=hint_font)
        lbl_ann_val.grid(row=1, column=1, sticky="e", padx=(10, 5))
        def update_ann_lbl(val):
            s_announce_int.set(int(float(val)))
            lbl_ann_val.config(text=f"Interval: {int(float(val))}s")
        ttk.Scale(frame_auto, from_=5, to=60, orient='horizontal', variable=s_announce_int, command=update_ann_lbl, length=self.px(120)).grid(row=1, column=2, sticky="w")

        ttk.Separator(frame_auto, orient="horizontal").grid(row=2, column=0, columnspan=3, sticky="ew", pady=15)
        ttk.Label(frame_auto, text="Party Chat Integration:").grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 5))
        ttk.Checkbutton(frame_auto, text="Announce New Cheaters to Party", variable=s_party_cheat_bool).grid(row=4, column=0, columnspan=3, sticky="w", padx=10, pady=2)
        ttk.Label(frame_auto, text="Notifies party chat when marked cheaters join or are already present in a server.", font=hint_font).grid(row=5, column=0, columnspan=3, sticky="w", padx=28, pady=(0, 5))
        ttk.Checkbutton(frame_auto, text="Announce Suspicious SourceBans to Party", variable=s_party_ban_bool).grid(row=6, column=0, columnspan=3, sticky="w", padx=10, pady=2)
        ttk.Label(frame_auto, text="Notifies party chat when players with suspicious bans join or are already present in a server.", font=hint_font).grid(row=7, column=0, columnspan=3, sticky="w", padx=28, pady=(0, 5))
        ttk.Label(frame_auto, text="Requires a SteamHistory API key and 'SteamHistory SourceBans Lookup' to be enabled", font=bold_hint_font).grid(row=8, column=0, columnspan=3, sticky="w", padx=28, pady=(0, 5))

        # ==========================================
        # SECTION 4: APPLICATION SETTINGS
        # ==========================================
        frame_app = create_section("Application Settings & Colors", 3)

        ttk.Label(frame_app, text="Local Userlist Data Settings:").grid(row=0, column=0, sticky="w", pady=(0, 5))

        p_frame = ttk.Frame(frame_app)
        p_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        ttk.Checkbutton(p_frame, text="Save Player Names", variable=s_save_names).pack(side="left", padx=(0, 15))
        ttk.Checkbutton(p_frame, text="Save Timestamps", variable=s_save_times).pack(side="left")

        ttk.Separator(frame_app, orient="horizontal").grid(row=2, column=0, sticky="ew", pady=5)

        ttk.Label(frame_app, text="UI Scale (Applied on Restart):").grid(row=3, column=0, sticky="w", pady=(0, 5))
        scale_cont = ttk.Frame(frame_app)
        scale_cont.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        lbl_ui_val = ttk.Label(scale_cont, text=f"{s_ui_scale.get():.2f}")
        lbl_ui_val.pack(side="right", padx=10)
        def update_ui_lbl(val):
            s_ui_scale.set(float(val))
            lbl_ui_val.config(text=f"{float(val):.2f}")
        ttk.Scale(scale_cont, from_=0.85, to=2.00, orient="horizontal", variable=s_ui_scale, command=update_ui_lbl, length=self.px(200)).pack(side="left", fill="x", expand=True)

        ttk.Separator(frame_app, orient="horizontal").grid(row=5, column=0, sticky="ew", pady=10)
        ttk.Label(frame_app, text="Player Highlighting:").grid(row=6, column=0, sticky="w", pady=(0, 5))
        color_grid = ttk.Frame(frame_app)
        color_grid.grid(row=7, column=0, sticky="ew")

        def pick_color(var, swatch_lbl):
            color = colorchooser.askcolor(initialcolor=var.get(), parent=self.window, title="Select Color")
            if color[1]:
                var.set(color[1])
                swatch_lbl.configure(background=color[1])
        def reset_color(var, swatch_lbl, default_hex):
            var.set(default_hex)
            swatch_lbl.configure(background=default_hex)
        def create_color_row(parent_fr, label_text, var, default_hex, row):
            lbl = ttk.Label(parent_fr, text=label_text)
            lbl.grid(row=row, column=0, sticky="w", pady=4)
            swatch = tk.Label(parent_fr, width=10, bg=var.get(), relief="solid", borderwidth=1)
            swatch.grid(row=row, column=1, padx=10, pady=4)
            btn_chg = ttk.Button(parent_fr, text="Change", width=8, command=lambda: pick_color(var, swatch))
            btn_chg.grid(row=row, column=2, padx=2, pady=4)
            btn_rst = ttk.Button(parent_fr, text="Reset", width=6, command=lambda: reset_color(var, swatch, default_hex))
            btn_rst.grid(row=row, column=3, padx=2, pady=4)

        defaults = DEFAULT_SETTINGS
        create_color_row(color_grid, "You (Self):", s_col_self, defaults['Color_Self'], 0)
        create_color_row(color_grid, "Marked Cheater:", s_col_cheater, defaults['Color_Cheater'], 1)
        create_color_row(color_grid, "Marked Suspicious:", s_col_sus, defaults['Color_Suspicious'], 2)
        create_color_row(color_grid, "Marked Other:", s_col_other, defaults['Color_Other'], 3)

        footer = ttk.Frame(self.window, padding=(10, 10))
        footer.grid(row=1, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        ttk.Button(footer, text="Cancel", command=self.window.destroy).grid(row=0, column=1, padx=(0, 10))
        ttk.Button(footer, text="Save Settings", command=save_and_close).grid(row=0, column=2)
