from __future__ import annotations

import multiprocessing as mp
import os
import queue
import shutil
import subprocess
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Optional

from . import __version__
from .backend import run_edl_backend
from .commands import CommandValidationError, ConnectionOptions, EdlCommandBuilder
from .device_detection import detect_qualcomm_9008
from .paths import bundled_path, default_workspace, user_data_dir
from .resource_pack import ModelProfile, ResourcePack, ResourcePackError

APP_TITLE = f"老八刷机工具 {__version__}"
UPSTREAM_URL = "https://github.com/bkerler/edl"


class LaobaApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1080x790")
        self.root.minsize(940, 680)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._process: Optional[mp.Process] = None
        self._pipe = None
        self._selected_profile: Optional[ModelProfile] = None
        self._model_map: dict[str, ModelProfile] = {}
        self._icon_image: Optional[tk.PhotoImage] = None
        self._resource: Optional[ResourcePack] = None

        self._configure_style()
        self._load_resources()
        self._build_ui()
        self._populate_brands()
        self._append_log("老八刷机工具已启动。请仅操作你拥有或获授权维修的设备。\n")
        if self._resource:
            info = self._resource.package_info
            self._append_log(
                f"内置资源包：发布者 {info.publisher}，版本 {info.version}，"
                f"机型 {len(self._resource.models)} 个。\n"
            )

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Header.TLabel", font=("Microsoft YaHei UI", 22, "bold"))
        style.configure("SubHeader.TLabel", font=("Microsoft YaHei UI", 10))
        style.configure("Danger.TButton", font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Status.TLabel", font=("Microsoft YaHei UI", 9))

    def _load_resources(self) -> None:
        try:
            icon_path = bundled_path("assets", "app_icon.ico")
            if icon_path.exists():
                self.root.iconbitmap(default=str(icon_path))
        except tk.TclError:
            pass
        try:
            png_path = bundled_path("assets", "app_icon.png")
            if png_path.exists():
                self._icon_image = tk.PhotoImage(file=str(png_path)).subsample(8, 8)
        except tk.TclError:
            self._icon_image = None

        try:
            self._resource = ResourcePack(
                bundled_path("assets", "qualcomm_resource_pack.zip"),
                user_data_dir() / "loader_cache",
            )
            self._resource.test_integrity()
        except ResourcePackError as exc:
            messagebox.showerror("资源包错误", str(exc), parent=self.root)
            self._resource = None

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))
        if self._icon_image:
            ttk.Label(header, image=self._icon_image).pack(side="left", padx=(0, 12))
        title_box = ttk.Frame(header)
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text="老八刷机工具", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            title_box,
            text="Qualcomm EDL / Sahara / Firehose 图形界面（基于 bkerler/edl）",
            style="SubHeader.TLabel",
        ).pack(anchor="w")
        self.device_status_var = tk.StringVar(value="9008：未检测")
        ttk.Label(header, textvariable=self.device_status_var, style="Status.TLabel").pack(
            side="right", anchor="ne", padx=8
        )

        selection = ttk.LabelFrame(outer, text="机型与连接", padding=10)
        selection.pack(fill="x", pady=(0, 8))
        selection.columnconfigure(1, weight=1)
        selection.columnconfigure(3, weight=1)
        selection.columnconfigure(5, weight=2)

        ttk.Label(selection, text="品牌").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.brand_var = tk.StringVar()
        self.brand_combo = ttk.Combobox(
            selection, textvariable=self.brand_var, state="readonly", width=22
        )
        self.brand_combo.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        self.brand_combo.bind("<<ComboboxSelected>>", self._on_brand_changed)

        ttk.Label(selection, text="系列").grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.series_var = tk.StringVar()
        self.series_combo = ttk.Combobox(
            selection, textvariable=self.series_var, state="readonly", width=22
        )
        self.series_combo.grid(row=0, column=3, sticky="ew", padx=(0, 10))
        self.series_combo.bind("<<ComboboxSelected>>", self._on_series_changed)

        ttk.Label(selection, text="机型").grid(row=0, column=4, sticky="w", padx=(0, 6))
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(
            selection, textvariable=self.model_var, state="readonly", width=38
        )
        self.model_combo.grid(row=0, column=5, sticky="ew")
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_changed)

        self.profile_info_var = tk.StringVar(value="请选择机型")
        ttk.Label(selection, textvariable=self.profile_info_var).grid(
            row=1, column=0, columnspan=6, sticky="w", pady=(8, 3)
        )

        ttk.Label(selection, text="连接").grid(row=2, column=0, sticky="w", padx=(0, 6))
        self.transport_var = tk.StringVar(value="USB")
        transport = ttk.Combobox(
            selection,
            textvariable=self.transport_var,
            values=("USB", "串口自动", "指定串口"),
            state="readonly",
            width=14,
        )
        transport.grid(row=2, column=1, sticky="w")
        transport.bind("<<ComboboxSelected>>", lambda _e: self._sync_transport_state())

        ttk.Label(selection, text="串口名").grid(row=2, column=2, sticky="e", padx=(6, 6))
        self.port_var = tk.StringVar()
        self.port_entry = ttk.Entry(selection, textvariable=self.port_var, width=18, state="disabled")
        self.port_entry.grid(row=2, column=3, sticky="w")

        ttk.Label(selection, text="LUN（可空）").grid(row=2, column=4, sticky="e", padx=(6, 6))
        self.lun_var = tk.StringVar()
        ttk.Entry(selection, textvariable=self.lun_var, width=8).grid(row=2, column=5, sticky="w")

        ttk.Button(selection, text="检测 9008", command=self._detect_device_async).grid(
            row=2, column=5, sticky="e"
        )

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="x", pady=(0, 8))
        self._build_basic_tab()
        self._build_backup_tab()
        self._build_qfil_tab()
        self._build_driver_tab()

        log_frame = ttk.LabelFrame(outer, text="运行日志", padding=8)
        log_frame.pack(fill="both", expand=True)
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=14,
            wrap="word",
            font=("Consolas", 9),
            state="disabled",
        )
        self.log_text.pack(fill="both", expand=True)

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(8, 0))
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(footer, textvariable=self.status_var).pack(side="left")
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=220)
        self.progress.pack(side="right", padx=(8, 0))
        self.stop_button = ttk.Button(
            footer, text="停止任务", command=self._stop_process, state="disabled"
        )
        self.stop_button.pack(side="right")

    def _build_basic_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="分区操作")
        tab.columnconfigure(1, weight=1)
        tab.columnconfigure(4, weight=1)

        ttk.Button(tab, text="读取分区表", command=self._run_print_gpt).grid(
            row=0, column=0, padx=(0, 8), pady=4, sticky="w"
        )
        ttk.Button(tab, text="重启设备", command=self._run_reset).grid(
            row=0, column=1, padx=(0, 8), pady=4, sticky="w"
        )

        ttk.Separator(tab, orient="horizontal").grid(
            row=1, column=0, columnspan=5, sticky="ew", pady=8
        )
        ttk.Label(tab, text="读取分区").grid(row=2, column=0, sticky="w")
        self.read_partition_var = tk.StringVar(value="boot_a")
        ttk.Entry(tab, textvariable=self.read_partition_var, width=18).grid(
            row=2, column=1, sticky="w", padx=(0, 8)
        )
        self.read_output_var = tk.StringVar(
            value=str(default_workspace() / "backup" / "boot_a.img")
        )
        ttk.Entry(tab, textvariable=self.read_output_var).grid(
            row=2, column=2, columnspan=2, sticky="ew", padx=(0, 6)
        )
        ttk.Button(tab, text="浏览", command=self._choose_read_output).grid(row=2, column=4, sticky="w")
        ttk.Button(tab, text="开始读取", command=self._run_read_partition).grid(
            row=3, column=2, sticky="w", pady=(5, 8)
        )

        ttk.Label(tab, text="写入分区").grid(row=4, column=0, sticky="w")
        self.write_partition_var = tk.StringVar(value="boot_a")
        ttk.Entry(tab, textvariable=self.write_partition_var, width=18).grid(
            row=4, column=1, sticky="w", padx=(0, 8)
        )
        self.write_image_var = tk.StringVar()
        ttk.Entry(tab, textvariable=self.write_image_var).grid(
            row=4, column=2, columnspan=2, sticky="ew", padx=(0, 6)
        )
        ttk.Button(tab, text="浏览", command=self._choose_write_image).grid(row=4, column=4, sticky="w")
        ttk.Button(tab, text="确认写入", command=self._run_write_partition).grid(
            row=5, column=2, sticky="w", pady=(5, 8)
        )

        ttk.Label(tab, text="擦除分区").grid(row=6, column=0, sticky="w")
        self.erase_partition_var = tk.StringVar(value="misc")
        ttk.Entry(tab, textvariable=self.erase_partition_var, width=18).grid(
            row=6, column=1, sticky="w", padx=(0, 8)
        )
        ttk.Button(tab, text="确认擦除", command=self._run_erase_partition).grid(
            row=6, column=2, sticky="w"
        )

    def _build_backup_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="整机备份/目录刷写")
        tab.columnconfigure(1, weight=1)

        ttk.Label(tab, text="备份目录").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.backup_dir_var = tk.StringVar(value=str(default_workspace() / "full_backup"))
        ttk.Entry(tab, textvariable=self.backup_dir_var).grid(row=0, column=1, sticky="ew", padx=(0, 6))
        ttk.Button(tab, text="浏览", command=self._choose_backup_dir).grid(row=0, column=2)

        ttk.Label(tab, text="跳过分区").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.skip_var = tk.StringVar(value="userdata")
        ttk.Entry(tab, textvariable=self.skip_var).grid(row=1, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(tab, text="开始备份", command=self._run_backup).grid(
            row=2, column=1, sticky="w", pady=(8, 12)
        )

        ttk.Separator(tab, orient="horizontal").grid(row=3, column=0, columnspan=3, sticky="ew", pady=6)
        ttk.Label(tab, text="镜像目录").grid(row=4, column=0, sticky="w", padx=(0, 8))
        self.flash_dir_var = tk.StringVar()
        ttk.Entry(tab, textvariable=self.flash_dir_var).grid(row=4, column=1, sticky="ew", padx=(0, 6))
        ttk.Button(tab, text="浏览", command=self._choose_flash_dir).grid(row=4, column=2)
        ttk.Button(tab, text="确认目录刷写", command=self._run_flash_folder).grid(
            row=5, column=1, sticky="w", pady=(8, 0)
        )

    def _build_qfil_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="QFIL XML 刷写")
        tab.columnconfigure(1, weight=1)

        self.rawprogram_var = tk.StringVar()
        self.patch_var = tk.StringVar()
        self.qfil_dir_var = tk.StringVar()
        rows = [
            ("rawprogram XML", self.rawprogram_var, self._choose_rawprogram),
            ("patch XML", self.patch_var, self._choose_patch),
            ("镜像目录", self.qfil_dir_var, self._choose_qfil_dir),
        ]
        for index, (label, var, callback) in enumerate(rows):
            ttk.Label(tab, text=label).grid(row=index, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Entry(tab, textvariable=var).grid(row=index, column=1, sticky="ew", padx=(0, 6), pady=4)
            ttk.Button(tab, text="浏览", command=callback).grid(row=index, column=2, pady=4)
        ttk.Button(tab, text="确认 QFIL 刷写", command=self._run_qfil).grid(
            row=3, column=1, sticky="w", pady=(8, 0)
        )

    def _build_driver_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="驱动与说明")
        tab.columnconfigure(0, weight=1)
        ttk.Label(
            tab,
            text=(
                "应用本身无需安装 Python 或 Git；真正连接 9008 设备时，Windows 仍需合适的 "
                "Qualcomm/WinUSB 驱动。驱动安装会单独请求管理员权限。"
            ),
            wraplength=850,
            justify="left",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        ttk.Button(tab, text="检测 9008 设备", command=self._detect_device_async).grid(
            row=1, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Button(tab, text="安装/修复内置驱动", command=self._install_drivers).grid(
            row=1, column=1, sticky="w", padx=(0, 8)
        )
        ttk.Button(tab, text="打开上游项目", command=lambda: webbrowser.open(UPSTREAM_URL)).grid(
            row=1, column=2, sticky="w"
        )
        ttk.Label(
            tab,
            text=(
                "限制：仅提供常规读取、写入、擦除、整机备份和 QFIL 刷写；不实现厂商认证绕过。"
                "资源配置中标记为需授权的机型，必须使用厂商或维修授权。"
            ),
            wraplength=850,
            justify="left",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(12, 0))

    def _populate_brands(self) -> None:
        if not self._resource:
            return
        brands = self._resource.brands()
        self.brand_combo["values"] = brands
        if brands:
            self.brand_var.set(brands[0])
            self._on_brand_changed()

    def _on_brand_changed(self, _event=None) -> None:
        if not self._resource:
            return
        series = self._resource.series_for(self.brand_var.get())
        self.series_combo["values"] = series
        if series:
            self.series_var.set(series[0])
            self._on_series_changed()

    def _on_series_changed(self, _event=None) -> None:
        if not self._resource:
            return
        models = self._resource.models_for(self.brand_var.get(), self.series_var.get())
        self._model_map = {model.display_name: model for model in models}
        self.model_combo["values"] = list(self._model_map)
        if models:
            self.model_var.set(models[0].display_name)
            self._on_model_changed()

    def _on_model_changed(self, _event=None) -> None:
        self._selected_profile = self._model_map.get(self.model_var.get())
        if not self._selected_profile:
            self.profile_info_var.set("请选择机型")
            return
        profile = self._selected_profile
        auth_text = profile.auth or "None"
        self.profile_info_var.set(
            f"存储：{profile.storage}　授权：{auth_text}　说明：{profile.description or '无'}　"
            f"引导：{profile.loader}"
        )

    def _sync_transport_state(self) -> None:
        state = "normal" if self.transport_var.get() == "指定串口" else "disabled"
        self.port_entry.configure(state=state)

    def _connection_options(self) -> ConnectionOptions:
        transport_map = {"USB": "usb", "串口自动": "serial", "指定串口": "port"}
        lun_text = self.lun_var.get().strip()
        try:
            lun = int(lun_text) if lun_text else None
        except ValueError as exc:
            raise CommandValidationError("LUN 必须是整数") from exc
        return ConnectionOptions(
            transport=transport_map.get(self.transport_var.get(), "usb"),
            port_name=self.port_var.get(),
            lun=lun,
        )

    def _builder(self) -> EdlCommandBuilder:
        if self._process and self._process.is_alive():
            raise CommandValidationError("已有任务正在运行")
        if not self._resource or not self._selected_profile:
            raise CommandValidationError("请先选择机型")
        profile = self._selected_profile
        if profile.auth.casefold() not in {"", "none"}:
            accepted = messagebox.askokcancel(
                "机型需要授权",
                f"资源配置标记该机型授权方案为“{profile.auth}”。\n\n"
                "本工具不会绕过厂商认证。请确认你已有合法授权，再继续尝试。",
                parent=self.root,
            )
            if not accepted:
                raise CommandValidationError("已取消：未确认厂商授权")
        loader = self._resource.extract_loader(profile)
        return EdlCommandBuilder(profile, loader, self._connection_options())

    def _start_command(self, args: list[str], description: str) -> None:
        workspace = default_workspace()
        self._append_log("\n" + "=" * 72 + "\n")
        self._append_log(f"任务：{description}\n")
        self._append_log("命令：edl " + " ".join(self._quote_log_arg(x) for x in args) + "\n")
        self.status_var.set(f"运行中：{description}")
        self.progress.start(12)
        self.stop_button.configure(state="normal")

        parent_conn, child_conn = mp.Pipe(duplex=False)
        process = mp.Process(
            target=run_edl_backend,
            args=(child_conn, args, str(workspace)),
            daemon=True,
        )
        process.start()
        child_conn.close()
        self._process = process
        self._pipe = parent_conn
        self.root.after(100, self._poll_backend)

    @staticmethod
    def _quote_log_arg(value: str) -> str:
        return f'"{value}"' if any(ch.isspace() for ch in value) else value

    def _poll_backend(self) -> None:
        if self._pipe:
            try:
                while self._pipe.poll():
                    message = self._pipe.recv()
                    if not isinstance(message, tuple):
                        continue
                    if message[0] == "log":
                        self._append_log(message[2])
                    elif message[0] == "exit":
                        self._finish_process(int(message[1]))
                        return
            except (EOFError, OSError):
                pass
        if self._process and self._process.is_alive():
            self.root.after(100, self._poll_backend)
        elif self._process:
            self._finish_process(self._process.exitcode or 0)

    def _finish_process(self, return_code: int) -> None:
        if self._process:
            self._process.join(timeout=0.2)
        if self._pipe:
            try:
                self._pipe.close()
            except OSError:
                pass
        self._process = None
        self._pipe = None
        self.progress.stop()
        self.stop_button.configure(state="disabled")
        if return_code == 0:
            self.status_var.set("任务完成")
            self._append_log("任务完成。\n")
        else:
            self.status_var.set(f"任务失败（代码 {return_code}）")
            self._append_log(f"任务结束，返回代码：{return_code}\n")

    def _stop_process(self) -> None:
        if self._process and self._process.is_alive():
            if not messagebox.askyesno("停止任务", "强制停止可能让设备处于未完成状态。确定停止？"):
                return
            self._process.terminate()
            self._process.join(timeout=2)
            self._append_log("任务已被用户强制停止。\n")
            self._finish_process(-1)

    def _run_with_builder(self, callback, description: str) -> None:
        try:
            builder = self._builder()
            args = callback(builder)
            self._start_command(args, description)
        except (CommandValidationError, ResourcePackError, OSError) as exc:
            messagebox.showerror("无法开始", str(exc), parent=self.root)

    def _run_print_gpt(self) -> None:
        self._run_with_builder(lambda b: b.print_gpt(), "读取分区表")

    def _run_reset(self) -> None:
        self._run_with_builder(lambda b: b.reset(), "重启设备")

    def _run_read_partition(self) -> None:
        self._run_with_builder(
            lambda b: b.read_partition(self.read_partition_var.get(), self.read_output_var.get()),
            f"读取分区 {self.read_partition_var.get().strip()}",
        )

    def _run_write_partition(self) -> None:
        partition = self.write_partition_var.get().strip()
        if not messagebox.askyesno(
            "写入分区确认",
            f"即将写入分区“{partition}”。错误镜像可能导致设备无法启动。\n\n确定继续？",
            icon="warning",
            parent=self.root,
        ):
            return
        self._run_with_builder(
            lambda b: b.write_partition(partition, self.write_image_var.get()),
            f"写入分区 {partition}",
        )

    def _run_erase_partition(self) -> None:
        partition = self.erase_partition_var.get().strip()
        typed = self._confirm_phrase(
            "擦除分区确认",
            f"即将永久擦除分区“{partition}”。输入 ERASE 继续：",
            "ERASE",
        )
        if not typed:
            return
        self._run_with_builder(lambda b: b.erase_partition(partition), f"擦除分区 {partition}")

    def _run_backup(self) -> None:
        self._run_with_builder(
            lambda b: b.backup_all(self.backup_dir_var.get(), self.skip_var.get()),
            "整机分区备份",
        )

    def _run_flash_folder(self) -> None:
        if not messagebox.askyesno(
            "目录刷写确认",
            "将按目录内分区文件进行批量写入。请确认镜像与机型完全匹配。\n\n确定继续？",
            icon="warning",
            parent=self.root,
        ):
            return
        self._run_with_builder(
            lambda b: b.flash_folder(self.flash_dir_var.get()),
            "目录批量刷写",
        )

    def _run_qfil(self) -> None:
        if not messagebox.askyesno(
            "QFIL 刷写确认",
            "QFIL XML 会执行多分区写入。请确认 rawprogram、patch 与镜像目录属于同一固件。\n\n确定继续？",
            icon="warning",
            parent=self.root,
        ):
            return
        self._run_with_builder(
            lambda b: b.qfil(
                self.rawprogram_var.get(), self.patch_var.get(), self.qfil_dir_var.get()
            ),
            "QFIL XML 刷写",
        )

    def _confirm_phrase(self, title: str, prompt: str, phrase: str) -> bool:
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        result = {"ok": False}
        ttk.Label(dialog, text=prompt, wraplength=430, justify="left").pack(
            padx=16, pady=(16, 8)
        )
        value = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=value, width=40)
        entry.pack(padx=16, pady=6)
        entry.focus_set()
        buttons = ttk.Frame(dialog)
        buttons.pack(padx=16, pady=(8, 16), fill="x")

        def accept() -> None:
            if value.get().strip() == phrase:
                result["ok"] = True
                dialog.destroy()
            else:
                messagebox.showerror("输入不匹配", f"必须输入 {phrase}", parent=dialog)

        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="继续", command=accept).pack(side="right", padx=(0, 8))
        dialog.bind("<Return>", lambda _e: accept())
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        self.root.wait_window(dialog)
        return result["ok"]

    def _detect_device_async(self) -> None:
        self.device_status_var.set("9008：检测中…")

        def worker() -> None:
            devices = detect_qualcomm_9008()
            self.root.after(0, lambda: self._show_detected_devices(devices))

        threading.Thread(target=worker, daemon=True).start()

    def _show_detected_devices(self, devices) -> None:
        if devices:
            self.device_status_var.set(f"9008：已连接 {len(devices)} 台")
            self._append_log("检测到 9008 设备：\n")
            for device in devices:
                self._append_log(f"  - {device.name} | {device.pnp_device_id}\n")
        else:
            self.device_status_var.set("9008：未检测")
            self._append_log("未检测到 Qualcomm 9008 设备。\n")

    def _install_drivers(self) -> None:
        if os.name != "nt":
            messagebox.showinfo("仅限 Windows", "驱动安装仅适用于 Windows。", parent=self.root)
            return
        source = bundled_path("drivers", "Windows")
        if not source.exists():
            messagebox.showwarning(
                "驱动未打包",
                "当前构建未包含上游 Drivers/Windows。请使用完整构建产物。",
                parent=self.root,
            )
            return
        target = user_data_dir() / "drivers" / "Windows"
        try:
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
        except OSError as exc:
            messagebox.showerror("驱动复制失败", str(exc), parent=self.root)
            return
        installer = target / "Install_Windows.bat"
        if installer.exists():
            try:
                import ctypes

                parameters = f'/c ""{installer}""'
                result = ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", "cmd.exe", parameters, str(target), 1
                )
                if result <= 32:
                    raise OSError(f"ShellExecuteW 返回 {result}")
                self._append_log(f"已启动驱动安装：{installer}\n")
            except OSError as exc:
                messagebox.showerror("无法启动驱动安装", str(exc), parent=self.root)
        else:
            os.startfile(target)  # type: ignore[attr-defined]
            messagebox.showinfo(
                "驱动目录",
                "已打开内置驱动目录。请按上游说明安装 WinUSB/QDLoader 驱动。",
                parent=self.root,
            )

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _choose_read_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="保存分区镜像",
            defaultextension=".img",
            filetypes=(("镜像文件", "*.img *.bin"), ("所有文件", "*.*")),
            initialdir=str(default_workspace()),
        )
        if path:
            self.read_output_var.set(path)

    def _choose_write_image(self) -> None:
        path = filedialog.askopenfilename(
            title="选择分区镜像",
            filetypes=(("镜像文件", "*.img *.bin"), ("所有文件", "*.*")),
        )
        if path:
            self.write_image_var.set(path)

    def _choose_backup_dir(self) -> None:
        path = filedialog.askdirectory(title="选择备份目录")
        if path:
            self.backup_dir_var.set(path)

    def _choose_flash_dir(self) -> None:
        path = filedialog.askdirectory(title="选择镜像目录")
        if path:
            self.flash_dir_var.set(path)

    def _choose_rawprogram(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 rawprogram XML", filetypes=(("XML", "*.xml"), ("所有文件", "*.*"))
        )
        if path:
            self.rawprogram_var.set(path)

    def _choose_patch(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 patch XML", filetypes=(("XML", "*.xml"), ("所有文件", "*.*"))
        )
        if path:
            self.patch_var.set(path)

    def _choose_qfil_dir(self) -> None:
        path = filedialog.askdirectory(title="选择 QFIL 镜像目录")
        if path:
            self.qfil_dir_var.set(path)

    def _on_close(self) -> None:
        if self._process and self._process.is_alive():
            if not messagebox.askyesno("退出", "任务仍在运行。强制停止并退出？", parent=self.root):
                return
            self._process.terminate()
            self._process.join(timeout=2)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
