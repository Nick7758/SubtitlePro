from PyQt5 import QtCore, QtGui, QtWidgets
from core.workers import VideoDownloadWorker
from typing import Optional
import time
import os
from config.settings import ASR_DICT, TRANS_DICT, DOWNLOAD_VIDEO_DIR
import platform


class UploadPage(QtWidgets.QWidget):
    """Video upload and translation page."""
    start_task = QtCore.pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        # Create widgets
        self.videoPath = QtWidgets.QLineEdit()
        self.videoPath.setPlaceholderText("请选择要翻译的视频文件...")
        self.videoBtn = QtWidgets.QPushButton("选择视频…")
        self.startBtn = QtWidgets.QPushButton("开始任务")
        self.startBtn.setEnabled(False)

        # Language selection
        self.langSrc = QtWidgets.QComboBox()
        for label, code in ASR_DICT:
            self.langSrc.addItem(label, code)
        self.langSrc.setCurrentIndex(0)
        self.langSrc.setMaximumWidth(150)  # 缩短下拉框宽度

        self.langTgt = QtWidgets.QComboBox()
        for label, code in TRANS_DICT:
            self.langTgt.addItem(label, code)
        self.langTgt.setCurrentIndex(0)
        self.langTgt.setMaximumWidth(150)  # 缩短下拉框宽度

        # Subtitle options
        self.burnCheck = QtWidgets.QCheckBox("合成硬字幕视频")
        self.burnCheck.setChecked(True)
        self.burnCheck.setToolTip("选中：生成带字幕的视频 (耗时)。\n不选中：仅生成 .srt/.ass 字幕文件 (极快)。")

        # Status and progress
        self.quotaLab = QtWidgets.QLabel("剩余分钟：—")
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.stepLab = QtWidgets.QLabel("就绪")
        self._seen_steps = set()
        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        self.openVideoBtn = QtWidgets.QPushButton("打开双语视频所在位置")
        self.openVideoBtn.setEnabled(False)
        self.openSubsBtn = QtWidgets.QPushButton("打开字幕所在位置")
        self.openSubsBtn.setEnabled(False)

        # Layout setup
        fileLay = QtWidgets.QHBoxLayout()
        fileLay.addWidget(self.videoPath)
        fileLay.addWidget(self.videoBtn)
        filew = QtWidgets.QWidget()
        filew.setLayout(fileLay)

        form = QtWidgets.QFormLayout()
        form.addRow("视频文件", filew)
        form.addRow("源语言", self.langSrc)
        form.addRow("翻译语言", self.langTgt)
        form.addRow("生成选项", self.burnCheck)

        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(self.startBtn)
        btns.addStretch(1)
        resultBtns = QtWidgets.QHBoxLayout()
        resultBtns.addWidget(self.openVideoBtn)
        resultBtns.addWidget(self.openSubsBtn)
        resultBtns.addStretch(1)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.quotaLab)
        lay.addLayout(form)
        lay.addLayout(btns)
        lay.addWidget(self.progress)
        lay.addWidget(self.stepLab)
        lay.addWidget(self.log)
        lay.addLayout(resultBtns)
        lay.addStretch(1)

        # Connect signals
        self.videoBtn.clicked.connect(self._select_file)
        self.startBtn.clicked.connect(self._start_task)

    def _reset_run_ui(self, initial_step="就绪"):
        self.progress.setValue(0)
        self.log.clear()
        self.stepLab.setText(initial_step)
        if hasattr(self, "_seen_steps"):
            self._seen_steps.clear()
        self.enableResultButtons(video_ok=False, subs_ok=False)

    def _select_file(self):
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择视频文件", "", "视频文件 (*.mp4 *.avi *.mov *.mkv)"
        )
        if file:
            self.videoPath.setText(file)
            self.startBtn.setEnabled(True)
            self._reset_run_ui("就绪")
            self.langSrc.setEnabled(True)
            self.langTgt.setEnabled(True)

    def _start_task(self):
        self._reset_run_ui("开始任务…")
        self.langSrc.setEnabled(False)
        self.langTgt.setEnabled(False)

        vp = self.videoPath.text().strip()
        if not vp or not os.path.exists(vp):
            self._log("请选择有效视频文件")
            self.langSrc.setEnabled(True)
            self.langTgt.setEnabled(True)
            return

        # Emit signal with parameters
        params = {
            "video_path": vp,
            "lang_src": self.langSrc.currentData(),
            "lang_tgt": self.langTgt.currentData(),
            "burn_subtitles": self.burnCheck.isChecked()
        }
        self.start_task.emit(params)

    def setProgress(self, value: int):
        self.progress.setValue(value)

    def setStep(self, text: str):
        self.stepLab.setText(text)
        if not hasattr(self, "_seen_steps"):
            self._seen_steps = set()
        if text not in self._seen_steps:
            self._seen_steps.add(text)
            self._log(text)

    def _log(self, text: str):
        self.log.append(f"[{time.strftime('%H:%M:%S')}] {text}")

    def setQuota(self, minutes: Optional[int]):
        if minutes is None:
            self.quotaLab.setText("剩余分钟：—")
        else:
            self.quotaLab.setText(f"剩余分钟：{minutes}")

    def enableResultButtons(self, video_ok: bool, subs_ok: bool):
        self.openVideoBtn.setEnabled(video_ok)
        self.openSubsBtn.setEnabled(subs_ok)


class DownloadPage(QtWidgets.QWidget):
    """Video download page."""
    start_download = QtCore.pyqtSignal(str)

    def __init__(self, ffmpeg_path="", parent=None):
        super().__init__(parent)
        self.ffmpeg_path = ffmpeg_path
        self.setup_ui()

    def setup_ui(self):
        # 使URL输入框具有占位符文本
        self.url_input = QtWidgets.QLineEdit()
        self.url_input.setPlaceholderText("在此粘贴视频链接 (YouTube, Bilibili, Twitter 等...)")
        self.download_btn = QtWidgets.QPushButton("下载视频")
        self.download_btn.clicked.connect(self._start_download)

        # Cookie状态标签
        self.cookie_label = QtWidgets.QLabel()

        # 同步和删除按钮
        self.sync_btn = QtWidgets.QPushButton("一键导入登录(youtube)")
        self.sync_btn.setObjectName("flatBtn")
        self.sync_btn.setToolTip("依次尝试从 Edge, Firefox 提取登录信息")

        self.delete_btn = QtWidgets.QPushButton("删除")
        self.delete_btn.setObjectName("dangerBtn")
        self.delete_btn.setMaximumWidth(60)
        self.delete_btn.setToolTip("删除现有无效的 Cookies 文件")
        self.delete_btn.clicked.connect(self._delete_cookies)

        # 进度条和状态标签
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setValue(0)
        self.status_label = QtWidgets.QLabel("就绪")

        # 日志显示区域
        self.log_display = QtWidgets.QTextEdit()
        self.log_display.setReadOnly(True)

        # 打开目录按钮
        self.open_folder_btn = QtWidgets.QPushButton("打开下载目录")
        self.open_folder_btn.setObjectName("flatBtn")
        self.open_folder_btn.clicked.connect(self._open_download_dir)

        # 布局设置
        form_layout = QtWidgets.QFormLayout()
        form_layout.addRow("视频链接", self.url_input)

        # Cookie状态布局
        cookie_layout = QtWidgets.QHBoxLayout()
        cookie_layout.addWidget(self.cookie_label)
        cookie_layout.addStretch(1)
        cookie_layout.addWidget(self.sync_btn)
        cookie_layout.addWidget(self.delete_btn)

        cookie_box = QtWidgets.QGroupBox("登录证书 ")
        cookie_box.setLayout(cookie_layout)

        # 按钮布局
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(self.download_btn)

        result_button_layout = QtWidgets.QHBoxLayout()
        result_button_layout.addWidget(self.open_folder_btn)
        result_button_layout.addStretch(1)

        # 主布局
        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form_layout)
        layout.addWidget(cookie_box)
        layout.addLayout(button_layout)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        layout.addWidget(self.log_display)
        layout.addLayout(result_button_layout)

        # 初始化Cookie状态
        self._refresh_cookie_status()

    def _refresh_cookie_status(self):
        """刷新Cookie状态显示"""
        import os
        work_dir = os.path.join(os.path.expanduser("~"), "Downloads", "DVP")
        c_path = os.path.join(work_dir, "cookies.txt")
        if os.path.exists(c_path) and os.path.getsize(c_path) > 0:
            size = os.path.getsize(c_path)
            self.cookie_label.setText(f"<span style='color:#00b894; font-weight:bold'>✔ 已加载完成 ({size}b)</span>")
            self.delete_btn.setEnabled(True)
        else:
            self.cookie_label.setText("<span style='color:#d63031'>✘ 需一键导入youtube登录信息 (限制视频可能下载失败)</span>")
            self.delete_btn.setEnabled(False)

    def _start_download(self):
        """开始下载视频"""
        url = self.url_input.text().strip()
        if not url:
            QtWidgets.QMessageBox.warning(self, "提示", "请输入链接")
            return
        self.download_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_display.clear()
        self._log("准备开始下载...")
        self.start_download.emit(url)

    def _delete_cookies(self):
        """删除Cookie文件"""
        reply = QtWidgets.QMessageBox.question(
            self, "确认删除",
            "确定要删除现有的Cookies文件吗？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self._log("已删除旧的 Cookies 文件。")
            self._refresh_cookie_status()
            QtWidgets.QMessageBox.information(self, "完成", "已删除旧的凭证，请重新点击同步。")

    def _open_download_dir(self):
        """打开下载目录"""
        if platform.system() == "Windows":
            os.startfile(DOWNLOAD_VIDEO_DIR)
        elif platform.system() == "Darwin":  # macOS
            os.system(f"open '{DOWNLOAD_VIDEO_DIR}'")
        else:  # Linux
            os.system(f"xdg-open '{DOWNLOAD_VIDEO_DIR}'")

    def _log(self, text: str):
        """添加日志信息"""
        import time
        self.log_display.append(f"[{time.strftime('%H:%M:%S')}] {text}")

    def set_progress(self, value: int):
        """设置进度条值"""
        self.progress_bar.setValue(value)


class BillingPage(QtWidgets.QWidget):
    """Billing and minutes purchase page."""
    purchase_minutes = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        self.balance_label = QtWidgets.QLabel("剩余分钟数: --")

        # 创建购买分钟数组件
        purchase_group = QtWidgets.QGroupBox("购买分钟")
        self.minutes_spin = QtWidgets.QSpinBox()
        self.minutes_spin.setRange(1, 100000)
        self.minutes_spin.setSingleStep(10)
        self.minutes_spin.setValue(60)
        self.purchase_btn = QtWidgets.QPushButton("购买分钟")
        self.purchase_btn.clicked.connect(self._purchase)

        # 使用QFormLayout排列购买分钟数相关控件
        form_layout = QtWidgets.QFormLayout(purchase_group)
        form_layout.addRow("分钟数", self.minutes_spin)
        form_layout.addRow(self.purchase_btn)

        # 创建主布局
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.balance_label)
        layout.addWidget(purchase_group)

        # 添加stretch将控件推到顶部
        layout.addStretch(1)

    def _purchase(self):
        minutes = self.minutes_spin.value()
        self.purchase_minutes.emit(minutes)

    def set_user(self, user):
        """设置用户信息并更新余额显示"""
        if user is None:
            self.balance_label.setText("剩余分钟数: --")
        else:
            self.balance_label.setText(f"剩余分钟数: {user.minutes_left}")


class SettingsPage(QtWidgets.QWidget):
    """Application settings page."""
    settings_changed = QtCore.pyqtSignal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setup_ui()

    def setup_ui(self):
        self.ffmpeg_input = QtWidgets.QLineEdit()
        self.ffmpeg_input.setText(self.config.get("ffmpeg_path", ""))

        self.workdir_input = QtWidgets.QLineEdit()
        self.workdir_input.setText(self.config.get("work_dir", ""))

        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])

        # 使用QFormLayout
        form = QtWidgets.QFormLayout()
        form.addRow("FFmpeg 路径:", self.ffmpeg_input)
        form.addRow("工作目录:", self.workdir_input)
        form.addRow("主题:", self.theme_combo)

        # 创建主布局
        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)

        # 保存按钮
        self.save_btn = QtWidgets.QPushButton("保存设置")
        self.save_btn.clicked.connect(self._save_settings)
        layout.addWidget(self.save_btn)

        # 恢复更新提醒按钮
        self.reset_update_btn = QtWidgets.QPushButton("恢复更新提醒")
        self.reset_update_btn.clicked.connect(self._reset_update_reminder)
        layout.addWidget(self.reset_update_btn)

        # 添加stretch将控件推到顶部
        layout.addStretch(1)

    def _browse_ffmpeg(self):
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择 FFmpeg 可执行文件", "", "Executable Files (*.exe)"
        )
        if file:
            self.ffmpeg_input.setText(file)

    def _browse_workdir(self):
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "选择工作目录")
        if directory:
            self.workdir_input.setText(directory)

    def _save_settings(self):
        self.config["ffmpeg_path"] = self.ffmpeg_input.text()
        self.config["work_dir"] = self.workdir_input.text()
        self.settings_changed.emit()

    def _reset_update_reminder(self):
        """恢复更新提醒"""
        # 清除跳过的版本记录
        if "skipped_version" in self.config:
            del self.config["skipped_version"]
            QtWidgets.QMessageBox.information(self, "成功", "已恢复更新提醒功能。")
        else:
            QtWidgets.QMessageBox.information(self, "提示", "暂无跳过的版本。")