from PyQt5 import QtCore, QtGui, QtWidgets
from core.workers import VideoDownloadWorker
from typing import Optional, List
import time
import os
from config.settings import ASR_DICT, TRANS_DICT, DOWNLOAD_VIDEO_DIR, SUB_RESULT_DIR
import platform
import srt
from core.subtitle_editor_logic import (
    parse_subtitle_file, 
    save_subtitle_file, 
    create_backup,
    swap_chinese_english,
    extract_chinese_only,
    extract_other_language_only,
    format_srt_time,
    parse_srt_time
)


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
            self, "选择视频文件", SUB_RESULT_DIR, "视频文件 (*.mp4 *.avi *.mov *.mkv)"
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

        # 获取语言选择
        lang_src = self.langSrc.currentData()
        lang_tgt = self.langTgt.currentData()
        
        # 验证：源语言和翻译语言不能同时为“无”
        if lang_src == "None" and lang_tgt == "None":
            QtWidgets.QMessageBox.warning(self, "参数错误", "源语言和翻译语言不能同时选择“无”，请至少选择一个语言。")
            self.langSrc.setEnabled(True)
            self.langTgt.setEnabled(True)
            return

        # Emit signal with parameters
        params = {
            "video_path": vp,
            "lang_src": lang_src,
            "lang_tgt": lang_tgt,
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


class SubtitleEditorPage(QtWidgets.QWidget):
    """Subtitle editor page for editing subtitle files."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = None
        self.current_format = None
        self.subtitles = []
        self.original_subtitles = []  # 保存原始字幕数据
        self.setup_ui()
    
    def setup_ui(self):
        # 文件选择区域
        self.file_input = QtWidgets.QLineEdit()
        self.file_input.setPlaceholderText("请选择字幕文件...")
        self.file_input.setReadOnly(True)
        
        self.select_file_btn = QtWidgets.QPushButton("选择字幕文件")
        self.select_file_btn.clicked.connect(self._select_subtitle_file)
        
        file_layout = QtWidgets.QHBoxLayout()
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(self.select_file_btn)
        
        # 表格显示区域
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["序号", "开始时间", "结束时间", "字幕内容1", "字幕内容2"])
        
        # 设置表格美化选项
        self.table.setAlternatingRowColors(True)  # 交替行颜色
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)  # 整行选择
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)  # 单行选择
        self.table.verticalHeader().setVisible(False)  # 隐藏垂直表头
        
        # 设置表头样式
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(QtCore.Qt.AlignCenter)  # 表头居中
        header.setStretchLastSection(True)  # 最后一列自动拉伸填充
        
        # 设置列宽策略和初始宽度
        self.table.setColumnWidth(0, 60)  # 序号列固定宽度
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Fixed)
        
        self.table.setColumnWidth(1, 140)  # 开始时间
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Interactive)
        
        self.table.setColumnWidth(2, 140)  # 结束时间
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Interactive)
        
        # 字幕内容列自动拉伸分配剩余空间
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.Stretch)
        
        # 设置表格可编辑
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | 
                                   QtWidgets.QAbstractItemView.EditKeyPressed)
        
        # 设置默认行高，确保文字完全显示
        self.table.verticalHeader().setDefaultSectionSize(35)
        
        # 自定义样式：文本选中颜色 + 确保编辑器文字完全可见
        self.table.setStyleSheet("""
            QTableWidget QLineEdit {
                selection-background-color: #B3D9FF;  /* 柔和的淡蓝色 */
                selection-color: #000000;  /* 黑色文字 */
                padding: 4px;  /* 内边距 */
                border: 1px solid #64B5F6;  /* 边框 */
                background-color: white;  /* 编辑时白色背景 */
            }
            QTableWidget::item {
                padding: 5px;  /* 单元格内边距 */
            }
        """)
        
        
        # 选项区域（用容器包装以便控制显示隐藏）
        self.options_widget = QtWidgets.QWidget()
        options_layout = QtWidgets.QHBoxLayout(self.options_widget)
        options_layout.setContentsMargins(0, 0, 0, 0)
        
        # 处理选项（动态更新）
        process_label = QtWidgets.QLabel("显示模式:")
        self.process_combo = QtWidgets.QComboBox()
        self.process_combo.addItem("中文在上", "chinese_up")
        self.process_combo.addItem("其他语言在上", "other_up")
        self.process_combo.addItem("仅中文", "chinese_only")
        self.process_combo.addItem("仅其他语言", "other_only")
        self.process_combo.setMaximumWidth(150)
        # 连接信号，选项改变时动态更新显示
        self.process_combo.currentIndexChanged.connect(self._on_display_mode_changed)
        
        # 保存格式选项
        format_label = QtWidgets.QLabel("保存格式:")
        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.addItem(".srt格式", "srt")
        self.format_combo.addItem(".ass格式", "ass")
        self.format_combo.addItem(".ssa格式", "ssa")
        self.format_combo.addItem(".vtt格式", "vtt")
        self.format_combo.setMaximumWidth(150)
        
        self.save_btn = QtWidgets.QPushButton("保存文件")
        self.save_btn.clicked.connect(self._save_file)
        self.save_btn.setEnabled(False)
        self.save_btn.setMaximumWidth(100)
        
        options_layout.addWidget(process_label)
        options_layout.addWidget(self.process_combo)
        options_layout.addStretch(1)
        options_layout.addWidget(format_label)
        options_layout.addWidget(self.format_combo)
        options_layout.addWidget(self.save_btn)
        
        # 状态标签（初始为空）
        self.status_label = QtWidgets.QLabel("")
        
        # 主布局
        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(file_layout)
        layout.addWidget(self.table)
        layout.addWidget(self.options_widget)
        layout.addWidget(self.status_label)
    
    def _select_subtitle_file(self):
        """选择字幕文件"""
        # 默认目录为字幕结果目录
        default_dir = SUB_RESULT_DIR if os.path.exists(SUB_RESULT_DIR) else os.path.expanduser("~")
        
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, 
            "选择字幕文件", 
            default_dir,
            "字幕文件 (*.srt *.ass *.ssa *.vtt);;所有文件 (*.*)"
        )
        
        if file:
            self._load_subtitle_file(file)
    
    def _load_subtitle_file(self, filepath: str):
        """加载字幕文件"""
        try:
            self.subtitles, self.current_format = parse_subtitle_file(filepath)
            self.current_file = filepath
            self.file_input.setText(filepath)
            
            # 保存原始字幕数据（深拷贝）
            import copy
            self.original_subtitles = copy.deepcopy(self.subtitles)
            
            # 重置显示模式为默认的“中文在上”
            self.process_combo.blockSignals(True)  # 阻止触发信号
            self.process_combo.setCurrentIndex(0)
            self.process_combo.blockSignals(False)
            
            # 更新表格
            self._update_table()
            
            # 根据加载的格式设置保存格式下拉框
            format_index = self.format_combo.findData(self.current_format)
            if format_index >= 0:
                self.format_combo.setCurrentIndex(format_index)
            
            self.save_btn.setEnabled(True)
            self.status_label.setText(f"已加载 {len(self.subtitles)} 条字幕")
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "加载失败", f"无法加载字幕文件:\n{str(e)}")
            self.status_label.setText("加载失败")
    
    def _update_table(self):
        """更新表格显示"""
        self.table.setRowCount(len(self.subtitles))
        
        for i, sub in enumerate(self.subtitles):
            # 序号
            seq_item = QtWidgets.QTableWidgetItem(str(sub.index))
            seq_item.setFlags(seq_item.flags() & ~QtCore.Qt.ItemIsEditable)  # 序号不可编辑
            self.table.setItem(i, 0, seq_item)
            
            # 开始时间
            start_item = QtWidgets.QTableWidgetItem(format_srt_time(sub.start))
            self.table.setItem(i, 1, start_item)
            
            # 结束时间
            end_item = QtWidgets.QTableWidgetItem(format_srt_time(sub.end))
            self.table.setItem(i, 2, end_item)
            
            # 字幕内容（分两行）
            content_lines = sub.content.split('\n', 1)
            content1 = content_lines[0] if len(content_lines) > 0 else ""
            content2 = content_lines[1] if len(content_lines) > 1 else ""
            
            self.table.setItem(i, 3, QtWidgets.QTableWidgetItem(content1))
            self.table.setItem(i, 4, QtWidgets.QTableWidgetItem(content2))
    
    def _on_display_mode_changed(self):
        """显示模式改变时动态更新显示"""
        if not self.original_subtitles:
            return
        
        try:
            # 从原始数据开始处理
            import copy
            temp_subtitles = copy.deepcopy(self.original_subtitles)
            
            # 获取处理选项
            process_option = self.process_combo.currentData()
            
            # 根据选项调用不同的处理函数
            if process_option == "chinese_up":
                self.subtitles = swap_chinese_english(temp_subtitles, True)
                mode_text = "中文在上"
            elif process_option == "other_up":
                self.subtitles = swap_chinese_english(temp_subtitles, False)
                mode_text = "其他语言在上"
            elif process_option == "chinese_only":
                self.subtitles = extract_chinese_only(temp_subtitles)
                mode_text = "仅中文"
            elif process_option == "other_only":
                self.subtitles = extract_other_language_only(temp_subtitles)
                mode_text = "仅其他语言"
            else:
                return
            
            # 更新表格显示
            self._update_table()
            
            self.status_label.setText(f"显示模式：{mode_text}")
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "显示错误", f"切换显示模式时出错:\n{str(e)}")
    
    def _process_subtitles(self):
        """处理字幕（交换中文/英文顺序或提取单一语言）"""
        if not self.subtitles:
            QtWidgets.QMessageBox.warning(self, "提示", "请先加载字幕文件")
            return
        
        try:
            # 先从表格读取当前的编辑内容
            self._read_table_to_subtitles()
            
            # 获取处理选项
            process_option = self.process_combo.currentData()
            
            # 根据选项调用不同的处理函数
            if process_option == "chinese_up":
                self.subtitles = swap_chinese_english(self.subtitles, True)
                order_text = "中文在上"
            elif process_option == "other_up":
                self.subtitles = swap_chinese_english(self.subtitles, False)
                order_text = "其他语言在上"
            elif process_option == "chinese_only":
                self.subtitles = extract_chinese_only(self.subtitles)
                order_text = "仅中文"
            elif process_option == "other_only":
                self.subtitles = extract_other_language_only(self.subtitles)
                order_text = "仅其他语言"
            else:
                return
            
            # 更新表格显示
            self._update_table()
            
            self.status_label.setText(f"已处理：{order_text}")
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "处理失败", f"处理字幕时出错:\n{str(e)}")
    
    def _read_table_to_subtitles(self):
        """从表格读取内容到字幕列表"""
        for i in range(self.table.rowCount()):
            try:
                # 读取时间
                start_str = self.table.item(i, 1).text()
                end_str = self.table.item(i, 2).text()
                
                # 解析时间
                start = parse_srt_time(start_str)
                end = parse_srt_time(end_str)
                
                # 读取内容
                content1 = self.table.item(i, 3).text() if self.table.item(i, 3) else ""
                content2 = self.table.item(i, 4).text() if self.table.item(i, 4) else ""
                
                # 组合内容
                if content2:
                    content = content1 + '\n' + content2
                else:
                    content = content1
                
                # 更新字幕对象
                self.subtitles[i].start = start
                self.subtitles[i].end = end
                self.subtitles[i].content = content
                
            except Exception as e:
                raise Exception(f"第 {i+1} 行数据格式错误: {str(e)}")
    
    def _save_file(self):
        """保存文件"""
        if not self.subtitles or not self.current_file:
            QtWidgets.QMessageBox.warning(self, "提示", "没有可保存的内容")
            return
        
        try:
            # 从表格读取最新的编辑内容
            self._read_table_to_subtitles()
            
            # 获取保存格式
            save_format = self.format_combo.currentData()
            
            # 创建备份
            try:
                backup_path = create_backup(self.current_file)
                self.status_label.setText(f"已创建备份: {os.path.basename(backup_path)}")
            except Exception as e:
                reply = QtWidgets.QMessageBox.question(
                    self,
                    "备份失败",
                    f"无法创建备份文件:\n{str(e)}\n\n是否继续保存？",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                )
                if reply != QtWidgets.QMessageBox.Yes:
                    return
            
            # 确定保存路径
            base_path = os.path.splitext(self.current_file)[0]
            save_path = f"{base_path}.{save_format}"
            
            # 保存文件
            save_subtitle_file(self.subtitles, save_path, save_format)
            
            QtWidgets.QMessageBox.information(
                self, 
                "保存成功", 
                f"字幕已保存为 {save_format.upper()} 格式:\n{save_path}"
            )
            self.status_label.setText(f"已保存: {os.path.basename(save_path)}")
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "保存失败", f"保存字幕文件时出错:\n{str(e)}")


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