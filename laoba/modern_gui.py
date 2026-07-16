from __future__ import annotations

import multiprocessing as mp
import os
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import customtkinter as ctk
from PIL import Image

from . import __version__
from .backend import run_edl_backend
from .commands import CommandValidationError, ConnectionOptions, EdlCommandBuilder
from .gui import LaobaApp as LegacyLaobaApp
from .paths import bundled_path, default_workspace, user_data_dir
from .resource_pack import ModelProfile, ResourcePack, ResourcePackError

APP_TITLE = f"老八刷机工具 {__version__}"
UPSTREAM_URL = "https://github.com/bkerler/edl"

BG = "#f6f7f9"
WHITE = "#ffffff"
PANEL = "#f4f5f7"
BORDER = "#e3e6ea"
TEXT = "#17191c"
MUTED = "#747981"
BLUE = "#006cff"
BLUE_HOVER = "#005bd9"
SELECTED = "#e4f1ff"
GREEN = "#12b83e"
RED = "#d93d3d"
FONT = "Microsoft YaHei UI"


class ModernLaobaApp(LegacyLaobaApp):
    """Reference-inspired interface while preserving the existing EDL backend."""

    def __init__(self) -> None:
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk(fg_color=BG)
        self.root.title(APP_TITLE)
        self.root.geometry("1500x900")
        self.root.minsize(1180, 720)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._process: Optional[mp.Process] = None
        self._pipe = None
        self._selected_profile: Optional[ModelProfile] = None
        self._model_map: dict[str, ModelProfile] = {}
        self._resource: Optional[ResourcePack] = None
        self._icon_image = None
        self._logo_image: Optional[ctk.CTkImage] = None
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._active_page = "flash"
        self._log_expanded = False

        self._init_variables()
        self._configure_modern_style()
        self._load_resources_modern()
        self._build_ui_modern()
        self._populate_brands()
        self._show_page("flash")
        self._append_log("老八刷机工具已启动。请仅操作你拥有或获授权维修的设备。\n")
        if self._resource:
            info = self._resource.package_info
            self._append_log(
                f"内置资源包：发布者 {info.publisher}，版本 {info.version}，"
                f"机型 {len(self._resource.models)} 个。\n"
            )

    def _init_variables(self) -> None:
        self.brand_var = tk.StringVar()
        self.series_var = tk.StringVar()
        self.model_var = tk.StringVar()
        self.model_display_var = tk.StringVar(value="已选择：[通用]-[AUTO]")
        self.profile_info_var = tk.StringVar(value="请选择设备/引导/配置")
        self.device_status_var = tk.StringVar(value="9008：未检测")
        self.transport_var = tk.StringVar(value="USB")
        self.port_var = tk.StringVar()
        self.lun_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="xml")
        self.search_partition_var = tk.StringVar()
        self.selected_count_var = tk.StringVar(value="已选择: 0")
        self.read_partition_var = tk.StringVar(value="boot_a")
        self.read_output_var = tk.StringVar(value=str(default_workspace() / "backup" / "boot_a.img"))
        self.write_partition_var = tk.StringVar(value="boot_a")
        self.write_image_var = tk.StringVar()
        self.erase_partition_var = tk.StringVar(value="misc")
        self.backup_dir_var = tk.StringVar(value=str(default_workspace() / "full_backup"))
        self.skip_var = tk.StringVar(value="userdata")
        self.flash_dir_var = tk.StringVar()
        self.rawprogram_var = tk.StringVar()
        self.patch_var = tk.StringVar()
        self.qfil_dir_var = tk.StringVar()
        self.status_var = tk.StringVar(value="就绪")
        self.log_bar_var = tk.StringVar(value="点击此处展开日志")

    def _configure_modern_style(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(
            "Modern.Treeview",
            background=WHITE,
            fieldbackground=WHITE,
            foreground=TEXT,
            borderwidth=0,
            rowheight=38,
            font=(FONT, 10),
        )
        style.configure(
            "Modern.Treeview.Heading",
            background=WHITE,
            foreground=MUTED,
            relief="flat",
            borderwidth=0,
            padding=(8, 10),
            font=(FONT, 10),
        )
        style.map("Modern.Treeview", background=[("selected", SELECTED)], foreground=[("selected", TEXT)])
        style.map("Modern.Treeview.Heading", background=[("active", PANEL)])
        style.configure(
            "Modern.Horizontal.TProgressbar",
            troughcolor="#e8eef7",
            background=BLUE,
            bordercolor="#e8eef7",
            lightcolor=BLUE,
            darkcolor=BLUE,
            thickness=4,
        )

    def _load_resources_modern(self) -> None:
        try:
            icon_path = bundled_path("assets", "app_icon.ico")
            if icon_path.exists():
                self.root.iconbitmap(default=str(icon_path))
        except tk.TclError:
            pass
        try:
            png_path = bundled_path("assets", "app_icon.png")
            if png_path.exists():
                image = Image.open(png_path)
                self._logo_image = ctk.CTkImage(light_image=image, dark_image=image, size=(72, 72))
        except (OSError, ValueError):
            self._logo_image = None

        try:
            self._resource = ResourcePack(
                bundled_path("assets", "qualcomm_resource_pack.zip"),
                user_data_dir() / "loader_cache",
            )
            self._resource.test_integrity()
        except ResourcePackError as exc:
            messagebox.showerror("资源包错误", str(exc), parent=self.root)
            self._resource = None

    def _build_ui_modern(self) -> None:
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

        sidebar = ctk.CTkFrame(self.root, width=236, corner_radius=0, fg_color=WHITE)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(10, weight=1)

        brand = ctk.CTkFrame(sidebar, height=132, corner_radius=0, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=22, pady=(22, 10))
        brand.grid_propagate(False)
        if self._logo_image:
            ctk.CTkLabel(brand, text="", image=self._logo_image).pack(side="left", padx=(0, 14), pady=18)
        title = ctk.CTkFrame(brand, fg_color="transparent")
        title.pack(side="left", fill="y")
        ctk.CTkLabel(title, text="老八", font=(FONT, 23, "bold"), text_color=TEXT).pack(anchor="w", pady=(25, 0))
        ctk.CTkLabel(title, text="刷机工具", font=(FONT, 10), text_color=MUTED).pack(anchor="w")

        self._add_nav(sidebar, 1, "home", "⌂", "首页")
        self._add_nav(sidebar, 2, "fastboot", "▣", "Fastboot")
        self._add_nav(sidebar, 3, "qc", "▣", "QC/高通")
        self._add_nav(sidebar, 4, "flash", "⚡", "深度刷机", indent=True)
        self._add_nav(sidebar, 5, "mtk", "▣", "MTK/联发科")
        self._add_nav(sidebar, 6, "settings", "⚙", "设置")
        self._add_nav(sidebar, 7, "donate", "♥", "捐赠")
        self._add_nav(sidebar, 8, "about", "ⓘ", "关于")

        ctk.CTkLabel(sidebar, text=f"v{__version__}", font=(FONT, 10), text_color=MUTED).grid(
            row=11, column=0, sticky="sw", padx=30, pady=25
        )

        self.content = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew", padx=18, pady=18)
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self._pages["flash"] = self._build_flash_page(self.content)
        self._pages["home"] = self._build_home_page(self.content)
        self._pages["fastboot"] = self._build_placeholder_page(self.content, "Fastboot", "Fastboot 模块将在后续版本中加入。")
        self._pages["mtk"] = self._build_placeholder_page(self.content, "MTK / 联发科", "当前版本专注 Qualcomm EDL，暂不包含 MTK 协议。")
        self._pages["settings"] = self._build_settings_page(self.content)
        self._pages["donate"] = self._build_placeholder_page(self.content, "捐赠", "感谢支持。此版本不内置付款或推广功能。")
        self._pages["about"] = self._build_about_page(self.content)

    def _add_nav(self, parent, row: int, key: str, icon: str, text: str, indent: bool = False) -> None:
        button = ctk.CTkButton(
            parent,
            text=f"{icon}   {text}",
            command=lambda k=("flash" if key == "qc" else key): self._show_page(k),
            height=46,
            corner_radius=6,
            anchor="w",
            fg_color="transparent",
            hover_color="#f1f6fc",
            text_color=TEXT,
            font=(FONT, 11),
        )
        button.grid(row=row, column=0, sticky="ew", padx=(34 if indent else 10, 10), pady=2)
        self._nav_buttons[key] = button

    def _show_page(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            return
        for candidate in self._pages.values():
            candidate.grid_remove()
        page.grid(row=0, column=0, sticky="nsew")
        self._active_page = key
        for nav_key, button in self._nav_buttons.items():
            selected = nav_key == key if key != "flash" else nav_key == "flash"
            button.configure(
                fg_color=SELECTED if selected else "transparent",
                text_color=BLUE if selected else TEXT,
                font=(FONT, 11, "bold" if selected else "normal"),
            )

    def _page(self, parent) -> ctk.CTkFrame:
        page = ctk.CTkFrame(parent, fg_color=WHITE, corner_radius=10, border_width=1, border_color=BORDER)
        page.grid_rowconfigure(0, weight=1)
        page.grid_columnconfigure(0, weight=1)
        return page

    def _action_button(self, parent, text: str, command, *, solid: bool = False, danger: bool = False):
        if solid:
            fg, hover, color = BLUE, BLUE_HOVER, WHITE
        elif danger:
            fg, hover, color = "#fff0f0", "#ffe1e1", RED
        else:
            fg, hover, color = PANEL, "#e9f2ff", BLUE
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            height=48,
            corner_radius=6,
            fg_color=fg,
            hover_color=hover,
            text_color=color,
            font=(FONT, 11, "bold"),
        )

    def _build_home_page(self, parent) -> ctk.CTkFrame:
        page = self._page(parent)
        body = ctk.CTkFrame(page, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=34, pady=30)
        for column in (0, 1):
            body.grid_columnconfigure(column, weight=1)
        ctk.CTkLabel(body, text="老八刷机工具", font=(FONT, 25, "bold"), text_color=TEXT).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ctk.CTkLabel(
            body,
            text="Qualcomm EDL / Sahara / Firehose 图形刷机工具",
            font=(FONT, 11),
            text_color=MUTED,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 24))
        cards = [
            ("内置资源包", f"{len(self._resource.models) if self._resource else 0} 个机型配置"),
            ("设备状态", "点击按钮检测 Qualcomm 9008"),
            ("构建方式", "单文件 EXE，无需 Python 或 Git"),
            ("安全说明", "写入前请备份；不绕过厂商认证"),
        ]
        for index, (title, value) in enumerate(cards):
            row, column = divmod(index, 2)
            card = ctk.CTkFrame(body, fg_color=BG, corner_radius=8, border_width=1, border_color=BORDER)
            card.grid(row=2 + row, column=column, sticky="nsew", padx=(0, 12) if column == 0 else (12, 0), pady=10)
            ctk.CTkLabel(card, text=title, font=(FONT, 10), text_color=MUTED).pack(anchor="w", padx=20, pady=(18, 4))
            ctk.CTkLabel(card, text=value, font=(FONT, 13, "bold"), text_color=TEXT, wraplength=430, justify="left").pack(
                anchor="w", padx=20, pady=(0, 20)
            )
        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.grid(row=4, column=0, columnspan=2, sticky="w", pady=(24, 0))
        self._action_button(actions, "进入深度刷机", lambda: self._show_page("flash"), solid=True).pack(side="left")
        self._action_button(actions, "检测 9008", self._detect_device_async).pack(side="left", padx=12)
        return page

    def _build_placeholder_page(self, parent, title: str, description: str) -> ctk.CTkFrame:
        page = self._page(parent)
        body = ctk.CTkFrame(page, fg_color="transparent")
        body.place(relx=0.5, rely=0.46, anchor="center")
        ctk.CTkLabel(body, text=title, font=(FONT, 25, "bold"), text_color=TEXT).pack()
        ctk.CTkLabel(body, text=description, font=(FONT, 11), text_color=MUTED).pack(pady=(10, 22))
        self._action_button(body, "返回深度刷机", lambda: self._show_page("flash")).pack()
        return page

    def _build_settings_page(self, parent) -> ctk.CTkFrame:
        page = self._page(parent)
        body = ctk.CTkFrame(page, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=34, pady=30)
        body.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(body, text="设置", font=(FONT, 24, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            body,
            text="程序本身没有运行前提；连接 9008 设备仍需要合适的 USB 驱动。",
            font=(FONT, 10),
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(5, 24))
        card = ctk.CTkFrame(body, fg_color=BG, corner_radius=8, border_width=1, border_color=BORDER)
        card.grid(row=2, column=0, sticky="ew")
        ctk.CTkLabel(card, text="驱动与工作目录", font=(FONT, 13, "bold"), text_color=TEXT).pack(
            anchor="w", padx=20, pady=(18, 5)
        )
        ctk.CTkLabel(card, text=f"工作目录：{default_workspace()}", font=(FONT, 10), text_color=MUTED).pack(
            anchor="w", padx=20
        )
        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.pack(anchor="w", padx=20, pady=18)
        self._action_button(buttons, "安装/修复内置驱动", self._install_drivers).pack(side="left")
        self._action_button(buttons, "打开工作目录", self._open_workspace).pack(side="left", padx=10)
        self._action_button(buttons, "检测 9008", self._detect_device_async).pack(side="left")
        return page

    def _build_about_page(self, parent) -> ctk.CTkFrame:
        page = self._page(parent)
        body = ctk.CTkFrame(page, fg_color="transparent")
        body.place(relx=0.5, rely=0.44, anchor="center")
        if self._logo_image:
            ctk.CTkLabel(body, text="", image=self._logo_image).pack(pady=(0, 12))
        ctk.CTkLabel(body, text="老八刷机工具", font=(FONT, 24, "bold"), text_color=TEXT).pack()
        ctk.CTkLabel(body, text=f"版本 {__version__}", font=(FONT, 10), text_color=MUTED).pack(pady=(5, 18))
        ctk.CTkLabel(
            body,
            text="基于 bkerler/edl，按 GPLv3 发布。仅用于合法设备维护与数据恢复。",
            font=(FONT, 10),
            text_color=MUTED,
            wraplength=700,
        ).pack()
        self._action_button(body, "打开上游项目", lambda: webbrowser.open(UPSTREAM_URL)).pack(pady=20)
        return page

    def _build_flash_page(self, parent) -> ctk.CTkFrame:
        page = self._page(parent)
        page.grid_rowconfigure(0, weight=1)
        page.grid_columnconfigure(0, weight=1)
        shell = ctk.CTkFrame(page, fg_color="transparent")
        shell.grid(row=0, column=0, sticky="nsew", padx=28, pady=(28, 0))
        shell.grid_rowconfigure(3, weight=1)
        shell.grid_columnconfigure(0, weight=1)

        self._build_device_toolbar(shell)
        self._build_source_toolbar(shell)
        self._build_partition_toolbar(shell)

        work = ctk.CTkFrame(shell, fg_color="transparent")
        work.grid(row=3, column=0, sticky="nsew", pady=(4, 0))
        work.grid_rowconfigure(0, weight=1)
        work.grid_columnconfigure(0, weight=1)

        table_frame = ctk.CTkFrame(work, fg_color=WHITE, corner_radius=0, border_width=1, border_color=BORDER)
        table_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 28))
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        columns = ("lun", "index", "label", "sector", "size", "file")
        self.partition_tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended", style="Modern.Treeview")
        headings = {
            "lun": ("LUN", 72),
            "index": ("#", 60),
            "label": ("标签", 210),
            "sector": ("起始扇区", 150),
            "size": ("大小", 120),
            "file": ("文件", 260),
        }
        for key, (title, width) in headings.items():
            self.partition_tree.heading(key, text=title)
            self.partition_tree.column(key, width=width, minwidth=60, anchor="center" if key != "file" else "w")
        self.partition_tree.grid(row=0, column=0, sticky="nsew")
        self.partition_tree.bind("<<TreeviewSelect>>", self._on_partition_selected)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.partition_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.partition_tree.configure(yscrollcommand=scroll.set)

        action_panel = ctk.CTkScrollableFrame(work, width=360, fg_color=WHITE, corner_radius=0, scrollbar_button_color="#cfd4da")
        action_panel.grid(row=0, column=1, sticky="nsew")
        self._build_action_panel(action_panel)

        self.progress = ttk.Progressbar(shell, mode="indeterminate", style="Modern.Horizontal.TProgressbar")
        self.progress.grid(row=4, column=0, sticky="ew", pady=(5, 0))

        log_host = ctk.CTkFrame(page, fg_color="transparent")
        log_host.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 12))
        log_host.grid_columnconfigure(0, weight=1)
        self.log_toggle = ctk.CTkButton(
            log_host,
            text=self.log_bar_var.get(),
            command=self._toggle_log,
            height=48,
            corner_radius=12,
            anchor="w",
            fg_color="#ecfff1",
            hover_color="#dcffe6",
            text_color=GREEN,
            font=(FONT, 11, "bold"),
        )
        self.log_toggle.grid(row=0, column=0, sticky="ew")
        self.log_bar_var.trace_add("write", lambda *_args: self.log_toggle.configure(text=self.log_bar_var.get()))
        self.log_text = ctk.CTkTextbox(
            log_host,
            height=180,
            corner_radius=8,
            fg_color="#11151a",
            text_color="#dce5ef",
            font=("Consolas", 10),
            wrap="word",
        )
        self.log_text.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.log_text.configure(state="disabled")
        self.log_text.grid_remove()
        return page

    def _build_device_toolbar(self, parent) -> None:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        bar.grid_columnconfigure(2, weight=1)
        self._action_button(bar, "选择设备/引导/配置", self._open_device_dialog).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(bar, textvariable=self.model_display_var, font=(FONT, 10, "bold"), text_color=TEXT).grid(
            row=0, column=1, sticky="w", padx=24
        )
        port = ctk.CTkFrame(bar, fg_color="transparent")
        port.grid(row=0, column=2, sticky="e")
        ctk.CTkLabel(port, text="端口:", font=(FONT, 10, "bold"), text_color=TEXT).pack(side="left", padx=(0, 8))
        ctk.CTkRadioButton(
            port,
            text="自动",
            variable=self.transport_var,
            value="USB",
            command=self._sync_transport_state,
            font=(FONT, 10),
            radiobutton_width=20,
            radiobutton_height=20,
        ).pack(side="left")
        ctk.CTkRadioButton(
            port,
            text="指定",
            variable=self.transport_var,
            value="指定串口",
            command=self._sync_transport_state,
            font=(FONT, 10),
            radiobutton_width=20,
            radiobutton_height=20,
        ).pack(side="left", padx=(8, 5))
        self.port_entry = ctk.CTkEntry(port, textvariable=self.port_var, width=245, height=42, corner_radius=5, fg_color=PANEL, border_color=BORDER)
        self.port_entry.pack(side="left", padx=(4, 8))
        self._action_button(port, "检测", self._detect_device_async).pack(side="left")
        ctk.CTkLabel(port, textvariable=self.device_status_var, font=(FONT, 9), text_color=MUTED).pack(side="left", padx=(9, 0))
        self._sync_transport_state()

    def _build_source_toolbar(self, parent) -> None:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkRadioButton(bar, text="使用XML", variable=self.mode_var, value="xml", font=(FONT, 10)).pack(side="left")
        self._action_button(bar, "选择XML", self._choose_xml_bundle).pack(side="left", padx=(7, 10))
        self._action_button(bar, "选择镜像目录", self._choose_qfil_dir).pack(side="left")
        ctk.CTkRadioButton(bar, text="使用设备分区表", variable=self.mode_var, value="device", font=(FONT, 10)).pack(side="left", padx=(14, 6))
        self._action_button(bar, "读取设备分区表", self._run_print_gpt).pack(side="left")
        ctk.CTkRadioButton(bar, text="使用自定义地址", variable=self.mode_var, value="custom", font=(FONT, 10)).pack(side="left", padx=(14, 0))

    def _build_partition_toolbar(self, parent) -> None:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkLabel(bar, text="搜索分区:", font=(FONT, 10), text_color=TEXT).pack(side="left")
        search = ctk.CTkEntry(bar, textvariable=self.search_partition_var, width=180, height=40, corner_radius=5, fg_color=PANEL, border_color=BORDER)
        search.pack(side="left", padx=(8, 14))
        ctk.CTkLabel(bar, textvariable=self.selected_count_var, font=(FONT, 10, "bold"), text_color=TEXT).pack(side="left")
        ctk.CTkCheckBox(bar, text="全选", command=self._select_all_partitions, font=(FONT, 10)).pack(side="left", padx=(10, 0))
        ctk.CTkCheckBox(bar, text="用户数据分区", font=(FONT, 10)).pack(side="left", padx=(10, 0))
        ctk.CTkCheckBox(bar, text="分区表", font=(FONT, 10)).pack(side="left", padx=(10, 0))
        ctk.CTkLabel(bar, text="LUN", font=(FONT, 10), text_color=MUTED).pack(side="right", padx=(8, 5))
        ctk.CTkEntry(bar, textvariable=self.lun_var, width=54, height=38, corner_radius=5, fg_color=PANEL, border_color=BORDER).pack(side="right")

    def _build_action_panel(self, parent) -> None:
        ctk.CTkLabel(parent, text="基础操作", font=(FONT, 12, "bold"), text_color=TEXT).pack(anchor="w", pady=(2, 12))
        self._action_button(parent, "读信息", self._run_print_gpt).pack(fill="x", pady=4)
        self._action_button(parent, "刷入（已选0）", self._run_write_selected).pack(fill="x", pady=4)
        self._action_button(parent, "刷入指定目录全部文件", self._run_flash_folder_quick).pack(fill="x", pady=4)
        self._action_button(parent, "回读（已选0）", self._run_read_selected).pack(fill="x", pady=4)
        options = ctk.CTkFrame(parent, fg_color="transparent")
        options.pack(fill="x", pady=(12, 9))
        ctk.CTkCheckBox(options, text="生成XML", font=(FONT, 10)).pack(side="left")
        ctk.CTkCheckBox(options, text="通用化", font=(FONT, 10)).pack(side="right")
        self._action_button(parent, "擦除（已选0） ⌄", self._run_erase_selected).pack(fill="x", pady=4)
        self._action_button(parent, "恢复出厂设置 ⌄", self._run_factory_reset).pack(fill="x", pady=4)
        self._action_button(parent, "重启 ⌄", self._run_reset).pack(fill="x", pady=4)
        ctk.CTkFrame(parent, height=1, fg_color=BORDER).pack(fill="x", pady=16)
        ctk.CTkLabel(parent, text="更多功能", font=(FONT, 12, "bold"), text_color=TEXT).pack(anchor="w", pady=(0, 10))
        self._action_button(parent, "整机分区备份", self._open_backup_dialog).pack(fill="x", pady=3)
        self._action_button(parent, "QFIL XML 刷写", self._open_qfil_dialog).pack(fill="x", pady=3)
        self._action_button(parent, "安装/修复驱动", self._install_drivers).pack(fill="x", pady=3)
        self.stop_button = self._action_button(parent, "停止当前任务", self._stop_process, danger=True)
        self.stop_button.pack(fill="x", pady=(8, 3))
        self.stop_button.configure(state="disabled")
        ctk.CTkLabel(parent, textvariable=self.status_var, font=(FONT, 9), text_color=MUTED, wraplength=320, justify="left").pack(
            anchor="w", pady=(12, 0)
        )

    def _open_device_dialog(self) -> None:
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("选择设备 / 引导 / 配置")
        dialog.geometry("760x440")
        dialog.minsize(680, 410)
        dialog.transient(self.root)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text="选择设备 / 引导 / 配置", font=(FONT, 20, "bold"), text_color=TEXT).pack(
            anchor="w", padx=28, pady=(26, 6)
        )
        ctk.CTkLabel(
            dialog,
            text="选择内置 Firehose 引导。标记为需要授权的机型仍需合法厂商或维修授权。",
            font=(FONT, 10),
            text_color=MUTED,
        ).pack(anchor="w", padx=28, pady=(0, 22))

        form = ctk.CTkFrame(dialog, fg_color="transparent")
        form.pack(fill="x", padx=28)
        for column in (0, 1, 2):
            form.grid_columnconfigure(column, weight=1)
        brands = self._resource.brands() if self._resource else []
        local_brand = tk.StringVar(value=self.brand_var.get() or (brands[0] if brands else ""))
        local_series = tk.StringVar(value=self.series_var.get())
        local_model = tk.StringVar(value=self.model_var.get())
        local_map: dict[str, ModelProfile] = {}

        for index, title in enumerate(("品牌", "系列", "机型")):
            ctk.CTkLabel(form, text=title, font=(FONT, 10, "bold"), text_color=TEXT).grid(row=0, column=index, sticky="w")
        brand_menu = ctk.CTkOptionMenu(form, variable=local_brand, values=brands or ["无"], height=42, fg_color=PANEL, button_color="#dfe4ea", text_color=TEXT)
        brand_menu.grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(6, 0))
        series_menu = ctk.CTkOptionMenu(form, variable=local_series, values=["无"], height=42, fg_color=PANEL, button_color="#dfe4ea", text_color=TEXT)
        series_menu.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(6, 0))
        model_menu = ctk.CTkOptionMenu(form, variable=local_model, values=["无"], height=42, fg_color=PANEL, button_color="#dfe4ea", text_color=TEXT)
        model_menu.grid(row=1, column=2, sticky="ew", pady=(6, 0))
        details = tk.StringVar(value=self.profile_info_var.get())
        ctk.CTkLabel(
            dialog,
            textvariable=details,
            fg_color=BG,
            corner_radius=7,
            font=(FONT, 10),
            text_color=TEXT,
            justify="left",
            anchor="w",
            wraplength=660,
            height=110,
        ).pack(fill="x", padx=28, pady=22)

        def update_details() -> None:
            profile = local_map.get(local_model.get())
            if profile:
                details.set(
                    f"存储：{profile.storage}　授权：{profile.auth or 'None'}\n"
                    f"说明：{profile.description or '无'}\n引导：{profile.loader}"
                )
            else:
                details.set("请选择机型")

        def update_models(value=None) -> None:
            nonlocal local_map
            models = self._resource.models_for(local_brand.get(), local_series.get()) if self._resource else []
            local_map = {model.display_name: model for model in models}
            values = list(local_map) or ["无"]
            model_menu.configure(values=values)
            if local_model.get() not in local_map:
                local_model.set(values[0])
            update_details()

        def update_series(value=None) -> None:
            values = self._resource.series_for(local_brand.get()) if self._resource else []
            series_menu.configure(values=values or ["无"])
            if local_series.get() not in values:
                local_series.set(values[0] if values else "无")
            update_models()

        brand_menu.configure(command=lambda value: (local_brand.set(value), update_series()))
        series_menu.configure(command=lambda value: (local_series.set(value), update_models()))
        model_menu.configure(command=lambda value: (local_model.set(value), update_details()))
        update_series()

        buttons = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons.pack(fill="x", padx=28, pady=(4, 24))

        def confirm() -> None:
            profile = local_map.get(local_model.get())
            if not profile:
                messagebox.showwarning("未选择机型", "请选择一个有效机型。", parent=dialog)
                return
            self.brand_var.set(local_brand.get())
            self.series_var.set(local_series.get())
            self.model_var.set(local_model.get())
            self._model_map = local_map
            self._selected_profile = profile
            self._on_model_changed()
            dialog.destroy()

        self._action_button(buttons, "取消", dialog.destroy).pack(side="right")
        self._action_button(buttons, "确认选择", confirm, solid=True).pack(side="right", padx=(0, 10))

    def _open_backup_dialog(self) -> None:
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("整机分区备份")
        dialog.geometry("680x310")
        dialog.transient(self.root)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text="整机分区备份", font=(FONT, 19, "bold"), text_color=TEXT).pack(anchor="w", padx=26, pady=(24, 16))
        form = ctk.CTkFrame(dialog, fg_color="transparent")
        form.pack(fill="x", padx=26)
        form.grid_columnconfigure(1, weight=1)
        self._dialog_field(form, 0, "备份目录", self.backup_dir_var, self._choose_backup_dir)
        self._dialog_field(form, 1, "跳过分区", self.skip_var, None)
        self._action_button(form, "开始备份", lambda: (dialog.destroy(), self._run_backup()), solid=True).grid(
            row=3, column=1, sticky="w", pady=(18, 0)
        )

    def _open_qfil_dialog(self) -> None:
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("QFIL XML 刷写")
        dialog.geometry("720x400")
        dialog.transient(self.root)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text="QFIL XML 刷写", font=(FONT, 19, "bold"), text_color=TEXT).pack(anchor="w", padx=26, pady=(24, 16))
        form = ctk.CTkFrame(dialog, fg_color="transparent")
        form.pack(fill="x", padx=26)
        form.grid_columnconfigure(1, weight=1)
        self._dialog_field(form, 0, "rawprogram XML", self.rawprogram_var, self._choose_rawprogram)
        self._dialog_field(form, 1, "patch XML", self.patch_var, self._choose_patch)
        self._dialog_field(form, 2, "镜像目录", self.qfil_dir_var, self._choose_qfil_dir)
        self._action_button(form, "确认 QFIL 刷写", lambda: (dialog.destroy(), self._run_qfil()), solid=True).grid(
            row=4, column=1, sticky="w", pady=(18, 0)
        )

    def _dialog_field(self, parent, row: int, label: str, variable: tk.StringVar, browse) -> None:
        ctk.CTkLabel(parent, text=label, font=(FONT, 10), text_color=TEXT).grid(row=row, column=0, sticky="w", pady=7)
        ctk.CTkEntry(parent, textvariable=variable, height=42, fg_color=PANEL, border_color=BORDER).grid(
            row=row, column=1, sticky="ew", padx=12, pady=7
        )
        if browse:
            self._action_button(parent, "浏览", browse).grid(row=row, column=2, pady=7)

    def _populate_brands(self) -> None:
        if not self._resource:
            return
        brands = self._resource.brands()
        if brands and self.brand_var.get() not in brands:
            self.brand_var.set(brands[0])
        self._on_brand_changed()

    def _on_brand_changed(self, _event=None) -> None:
        if not self._resource:
            return
        series = self._resource.series_for(self.brand_var.get())
        if series and self.series_var.get() not in series:
            self.series_var.set(series[0])
        self._on_series_changed()

    def _on_series_changed(self, _event=None) -> None:
        if not self._resource:
            return
        models = self._resource.models_for(self.brand_var.get(), self.series_var.get())
        self._model_map = {model.display_name: model for model in models}
        if models and self.model_var.get() not in self._model_map:
            self.model_var.set(models[0].display_name)
        self._on_model_changed()

    def _on_model_changed(self, _event=None) -> None:
        self._selected_profile = self._model_map.get(self.model_var.get())
        if not self._selected_profile:
            self.model_display_var.set("已选择：[通用]-[AUTO]")
            self.profile_info_var.set("请选择设备/引导/配置")
            return
        profile = self._selected_profile
        self.model_display_var.set(f"已选择：[{self.brand_var.get()}]-[{profile.display_name}]")
        self.profile_info_var.set(
            f"存储：{profile.storage}　授权：{profile.auth or 'None'}　说明：{profile.description or '无'}　引导：{profile.loader}"
        )

    def _sync_transport_state(self) -> None:
        if hasattr(self, "port_entry"):
            self.port_entry.configure(state="normal" if self.transport_var.get() == "指定串口" else "disabled")

    def _connection_options(self) -> ConnectionOptions:
        lun_text = self.lun_var.get().strip()
        try:
            lun = int(lun_text) if lun_text else None
        except ValueError as exc:
            raise CommandValidationError("LUN 必须是整数") from exc
        return ConnectionOptions(
            transport="port" if self.transport_var.get() == "指定串口" else "usb",
            port_name=self.port_var.get(),
            lun=lun,
        )

    def _builder(self) -> EdlCommandBuilder:
        if self._process and self._process.is_alive():
            raise CommandValidationError("已有任务正在运行")
        if not self._resource or not self._selected_profile:
            raise CommandValidationError("请先选择设备/引导/配置")
        profile = self._selected_profile
        if profile.auth.casefold() not in {"", "none"}:
            if not messagebox.askokcancel(
                "机型需要授权",
                f"资源配置标记该机型授权方案为“{profile.auth}”。\n\n本工具不会绕过厂商认证。请确认已有合法授权。",
                parent=self.root,
            ):
                raise CommandValidationError("已取消：未确认厂商授权")
        return EdlCommandBuilder(profile, self._resource.extract_loader(profile), self._connection_options())

    def _start_command(self, args: list[str], description: str) -> None:
        workspace = default_workspace()
        self._append_log("\n" + "=" * 72 + "\n")
        self._append_log(f"任务：{description}\n")
        self._append_log("命令：edl " + " ".join(self._quote_log_arg(x) for x in args) + "\n")
        self.status_var.set(f"运行中：{description}")
        self.log_bar_var.set(f"运行中：{description}（点击展开日志）")
        self.progress.start(12)
        self.stop_button.configure(state="normal")
        parent_conn, child_conn = mp.Pipe(duplex=False)
        process = mp.Process(target=run_edl_backend, args=(child_conn, args, str(workspace)), daemon=True)
        process.start()
        child_conn.close()
        self._process = process
        self._pipe = parent_conn
        self.root.after(100, self._poll_backend)

    def _finish_process(self, return_code: int) -> None:
        super()._finish_process(return_code)
        self.log_bar_var.set("任务完成，点击此处展开日志" if return_code == 0 else f"任务失败（代码 {return_code}），点击展开日志")

    def _toggle_log(self) -> None:
        self._log_expanded = not self._log_expanded
        if self._log_expanded:
            self.log_text.grid()
            self.log_bar_var.set("点击此处收起日志")
        else:
            self.log_text.grid_remove()
            self.log_bar_var.set("点击此处展开日志")

    def _append_log(self, text: str) -> None:
        if not hasattr(self, "log_text"):
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _on_partition_selected(self, _event=None) -> None:
        count = len(self.partition_tree.selection())
        self.selected_count_var.set(f"已选择: {count}")
        if count:
            values = self.partition_tree.item(self.partition_tree.selection()[0], "values")
            if len(values) >= 3:
                self.search_partition_var.set(str(values[2]))

    def _select_all_partitions(self) -> None:
        items = self.partition_tree.get_children()
        if items:
            self.partition_tree.selection_set(items)
            self._on_partition_selected()

    def _current_partition(self, fallback: str) -> str:
        selected = self.partition_tree.selection()
        if selected:
            values = self.partition_tree.item(selected[0], "values")
            if len(values) >= 3 and str(values[2]).strip():
                return str(values[2]).strip()
        return self.search_partition_var.get().strip() or fallback

    def _run_read_selected(self) -> None:
        partition = self._current_partition(self.read_partition_var.get())
        path = filedialog.asksaveasfilename(
            title=f"保存分区 {partition}",
            initialfile=f"{partition}.img",
            initialdir=str(default_workspace()),
            defaultextension=".img",
            filetypes=(("镜像文件", "*.img *.bin"), ("所有文件", "*.*")),
        )
        if path:
            self.read_partition_var.set(partition)
            self.read_output_var.set(path)
            self._run_read_partition()

    def _run_write_selected(self) -> None:
        partition = self._current_partition(self.write_partition_var.get())
        self.write_partition_var.set(partition)
        self._choose_write_image()
        if self.write_image_var.get():
            self._run_write_partition()

    def _run_erase_selected(self) -> None:
        self.erase_partition_var.set(self._current_partition(self.erase_partition_var.get()))
        self._run_erase_partition()

    def _run_factory_reset(self) -> None:
        if messagebox.askyesno(
            "恢复出厂设置",
            "将擦除 userdata 分区，用户数据会永久丢失。\n\n确定继续？",
            icon="warning",
            parent=self.root,
        ):
            self._run_with_builder(lambda b: b.erase_partition("userdata"), "擦除 userdata（恢复出厂设置）")

    def _run_flash_folder_quick(self) -> None:
        self._choose_flash_dir()
        if self.flash_dir_var.get():
            self._run_flash_folder()

    def _choose_xml_bundle(self) -> None:
        self._choose_rawprogram()
        if self.rawprogram_var.get():
            self._choose_patch()

    def _open_workspace(self) -> None:
        path = default_workspace()
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            webbrowser.open(path.as_uri())
