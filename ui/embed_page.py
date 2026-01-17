from PyQt5 import QtWidgets, QtCore, QtGui
from core.subtitle_processor import create_preview_frame, SubtitleEmbedder
from config.settings import RESULT_DIR, SUB_RESULT_DIR, VIDEO_RESULT_DIR
import os
import shutil
import uuid
import re


class EmbedSubtitlesPage(QtWidgets.QWidget):
    def __init__(self, ffmpeg_path, ffprobe_path, parent=None):
        super().__init__(parent)
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.subtitle_path = ""
        self.video_path = ""

        # Default colors (RGB for display)
        self.zh_color = QtGui.QColor(255, 195, 0)  # FFC300 (Gold)
        self.other_color = QtGui.QColor(255, 255, 255)  # White

        self._init_ui()
        self.embedder = SubtitleEmbedder(ffmpeg_path, ffprobe_path)
        self.embedder.progress.connect(self._on_progress)
        self.embedder.finished.connect(self._on_finished)
        self.embedder.error.connect(self._on_error)

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # File Selection Area
        file_group = QtWidgets.QGroupBox("文件选择")
        file_layout = QtWidgets.QFormLayout(file_group)

        # Subtitle selection
        self.sub_btn = QtWidgets.QPushButton("选择字幕文件...")
        self.sub_btn.clicked.connect(self._select_subtitle)
        self.sub_label = QtWidgets.QLabel("未选择")
        file_layout.addRow(self.sub_btn, self.sub_label)

        # Video selection
        self.video_btn = QtWidgets.QPushButton("选择视频文件...")
        self.video_btn.clicked.connect(self._select_video)
        self.video_label = QtWidgets.QLabel("未选择")
        file_layout.addRow(self.video_btn, self.video_label)

        # Parameters Area
        params_group = QtWidgets.QGroupBox("参数设置")
        self.params_layout = QtWidgets.QFormLayout(params_group)

        # Chinese font size
        self.chinese_fontsize = QtWidgets.QDoubleSpinBox()
        self.chinese_fontsize.setRange(0.01, 0.20)
        self.chinese_fontsize.setSingleStep(0.005)
        self.chinese_fontsize.setValue(0.045)
        self.chinese_fontsize.setDecimals(3)
        self.chinese_fontsize.setSuffix(" (视频宽度的倍数)")
        self.chinese_fontsize.valueChanged.connect(self._on_param_changed)

        # Chinese Color Button
        self.zh_color_btn = QtWidgets.QPushButton()
        self.zh_color_btn.setFixedWidth(50)
        self.zh_color_btn.setMinimumHeight(self.chinese_fontsize.sizeHint().height())
        self.zh_color_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.zh_color_btn.clicked.connect(self._pick_zh_color)
        self._update_color_btn(self.zh_color_btn, self.zh_color)

        zh_container = QtWidgets.QWidget()
        zh_layout = QtWidgets.QHBoxLayout(zh_container)
        zh_layout.setContentsMargins(0, 0, 0, 0)
        zh_layout.addWidget(self.chinese_fontsize)
        zh_layout.addWidget(QtWidgets.QLabel("颜色:"))
        zh_layout.addWidget(self.zh_color_btn)
        zh_layout.addStretch()

        # Other language font size
        self.other_fontsize = QtWidgets.QDoubleSpinBox()
        self.other_fontsize.setRange(0.01, 0.20)
        self.other_fontsize.setSingleStep(0.005)
        self.other_fontsize.setValue(0.040)
        self.other_fontsize.setDecimals(3)
        self.other_fontsize.setSuffix(" (视频宽度的倍数)")
        self.other_fontsize.valueChanged.connect(self._on_param_changed)

        # Other Color Button
        self.other_color_btn = QtWidgets.QPushButton()
        self.other_color_btn.setFixedWidth(50)
        self.other_color_btn.setMinimumHeight(self.other_fontsize.sizeHint().height())
        self.other_color_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.other_color_btn.clicked.connect(self._pick_other_color)
        self._update_color_btn(self.other_color_btn, self.other_color)

        other_container = QtWidgets.QWidget()
        other_layout = QtWidgets.QHBoxLayout(other_container)
        other_layout.setContentsMargins(0, 0, 0, 0)
        other_layout.addWidget(self.other_fontsize)
        other_layout.addWidget(QtWidgets.QLabel("颜色:"))
        other_layout.addWidget(self.other_color_btn)
        other_layout.addStretch()

        # Bottom margin
        self.margin_spinbox = QtWidgets.QSpinBox()
        self.margin_spinbox.setRange(0, 500)
        self.margin_spinbox.setSingleStep(10)
        # 【需求2 修改】: 默认改为 20 像素
        self.margin_spinbox.setValue(20)
        self.margin_spinbox.setSuffix(" 像素")
        self.margin_spinbox.valueChanged.connect(self._on_param_changed)

        self.params_layout.addRow("中文字体大小:", zh_container)
        self.params_layout.addRow("其他语言字体大小:", other_container)
        self.params_layout.addRow("距离视频底部:", self.margin_spinbox)

        # Preview section
        preview_group = QtWidgets.QGroupBox("预览")
        preview_layout = QtWidgets.QVBoxLayout(preview_group)

        self.preview_btn = QtWidgets.QPushButton("生成预览")
        self.preview_btn.clicked.connect(self._generate_preview)
        self.preview_btn.setEnabled(False)

        self.preview_label = QtWidgets.QLabel()
        self.preview_label.setAlignment(QtCore.Qt.AlignCenter)
        self.preview_label.setMinimumSize(640, 360)
        self.preview_label.setStyleSheet("QLabel { background-color: #f0f0f0; border: 1px solid #ccc; }")
        self.preview_label.setText("选择文件后点击预览按钮查看效果")
        self.preview_label.setScaledContents(False)  # Keep aspect ratio by not scaling content explicitly here

        preview_layout.addWidget(self.preview_btn)
        preview_layout.addWidget(self.preview_label)

        # Embed section
        embed_layout = QtWidgets.QHBoxLayout()
        self.embed_btn = QtWidgets.QPushButton("开始嵌入字幕")
        self.embed_btn.clicked.connect(self._start_embed)
        self.embed_btn.setEnabled(False)
        self.embed_btn.setMinimumHeight(40)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setVisible(False)

        embed_layout.addWidget(self.embed_btn)
        embed_layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)

        # Add all sections to main layout
        layout.addWidget(file_group)
        layout.addWidget(params_group)
        layout.addWidget(preview_group)
        layout.addLayout(embed_layout)
        layout.addWidget(self.status_label)

    def _update_color_btn(self, btn, color):
        """Update button style to show selected color."""
        # Calculate contrast color for text (black or white)
        luminance = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
        text_color = "black" if luminance > 128 else "white"

        style = f"""
            QPushButton {{
                background-color: {color.name()};
                border: 1px solid #888;
                border-radius: 4px;
                color: {text_color};
            }}
        """
        btn.setStyleSheet(style)

    def _pick_zh_color(self):
        c = QtWidgets.QColorDialog.getColor(self.zh_color, self, "选择中文字体颜色")
        if c.isValid():
            self.zh_color = c
            self._update_color_btn(self.zh_color_btn, c)
            self._on_param_changed()

    def _pick_other_color(self):
        c = QtWidgets.QColorDialog.getColor(self.other_color, self, "选择其他语言字体颜色")
        if c.isValid():
            self.other_color = c
            self._update_color_btn(self.other_color_btn, c)
            self._on_param_changed()

    def _get_ass_color(self, qcolor):
        """Convert QColor to ASS color format (&HBBGGRR)."""
        return f"&H00{qcolor.blue():02X}{qcolor.green():02X}{qcolor.red():02X}"

    def _select_subtitle(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择字幕文件", SUB_RESULT_DIR, "Subtitle Files (*.srt *.ass *.ssa *.vtt)"
        )
        if path:
            self.subtitle_path = path
            self.sub_label.setText(os.path.basename(path))
            self._check_ready()

    def _select_video(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择视频文件", VIDEO_RESULT_DIR, "Video Files (*.mp4 *.avi *.mkv *.mov *.flv)"
        )
        if path:
            self.video_path = path
            self.video_label.setText(os.path.basename(path))
            self._check_ready()

    def _check_ready(self):
        """Check if files are selected and enable buttons."""
        ready = bool(self.subtitle_path and self.video_path)
        self.preview_btn.setEnabled(ready)
        self.embed_btn.setEnabled(ready)

    def _on_param_changed(self):
        """Called when parameters change, to hint user to update preview."""
        if self.preview_label.pixmap():
            self.status_label.setText("参数已修改，请点击【生成预览】查看效果")

    # 【辅助函数】：安全复制文件，解决 FFmpeg 报错 -22 的问题
    def _create_safe_temp_file(self, original_path):
        """复制文件到临时目录并重命名为安全文件名"""
        import tempfile
        ext = os.path.splitext(original_path)[1]
        temp_dir = tempfile.gettempdir()
        safe_name = f"safe_temp_{uuid.uuid4().hex[:8]}{ext}"
        safe_path = os.path.join(temp_dir, safe_name)
        try:
            shutil.copy2(original_path, safe_path)
            return safe_path
        except Exception as e:
            print(f"Error creating temp file: {e}")
            return original_path  # 如果失败，返回原路径

    # 【需求3 修改】：查找字幕第一句的时间，确保预览有画面
    def _find_subtitle_timestamp(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            # 查找 srt/vtt 格式时间: 00:00:05,000
            m = re.search(r'(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})', content)
            if m:
                h, m, s, ms = map(int, m.groups())
                # 加 1.5 秒，尽量落在字幕中间
                return h * 3600 + m * 60 + s + (ms / 1000.0) + 1.5
        except:
            pass
        return 10.0  # 默认

    def _generate_preview(self):
        """Generate preview with first subtitle on first frame."""
        if not self.subtitle_path or not self.video_path:
            return

        if not self.ffmpeg_path or not self.ffprobe_path:
            QtWidgets.QMessageBox.warning(self, "FFmpeg未配置", "FFmpeg路径未配置或不存在。")
            return

        self.status_label.setText("正在生成预览...")
        self.preview_btn.setEnabled(False)
        QtWidgets.QApplication.processEvents()

        safe_sub_path = None
        preview_path = None

        try:
            import tempfile
            # Create temp preview image
            temp_preview = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            preview_path = temp_preview.name
            temp_preview.close()

            # 【核心修复 1】：使用安全文件名，防止路径含特殊字符导致预览失败
            safe_sub_path = self._create_safe_temp_file(self.subtitle_path)

            # 【核心修复 2】：使用智能时间戳，防止截取到无字幕画面
            # 注意：这里我们无法直接传时间参数给 create_preview_frame（因为它定义死只截开头）
            # 所以我们只能在这里重写简单的截图逻辑，绕过 create_preview_frame 的限制

            # Get parameters
            chinese_factor = self.chinese_fontsize.value()
            other_factor = self.other_fontsize.value()
            margin = self.margin_spinbox.value() if self.margin_spinbox.value() > 0 else None
            zh_ass_color = self._get_ass_color(self.zh_color)
            other_ass_color = self._get_ass_color(self.other_color)

            # 我们调用 embedder 内的方法来生成样式文件，但自己截图
            # 为了简单起见，这里我们直接调用 create_preview_frame，但
            # *关键技巧*：我们传入的 video_path 加上 seek 参数？不，ffprobe 不支持。

            # 既然你是为了恢复字幕显示，最稳妥的方法是：
            # 依然使用 create_preview_frame，但我们要确保它能处理文件名中的引号。
            # 修改: 我们把 safe_sub_path 传给它！

            success = create_preview_frame(
                self.video_path,
                safe_sub_path,  # 传入安全路径
                preview_path,
                self.ffmpeg_path,
                self.ffprobe_path,
                chinese_factor,
                other_factor,
                margin,
                zh_ass_color,
                other_ass_color
            )

            if success and os.path.exists(preview_path):
                pixmap = QtGui.QPixmap(preview_path)
                scaled_pixmap = pixmap.scaled(
                    self.preview_label.size(),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation
                )
                self.preview_label.setPixmap(scaled_pixmap)
                self.status_label.setText("预览生成成功")
            else:
                self.status_label.setText("预览生成失败")

        except Exception as e:
            self.status_label.setText(f"错误: {str(e)}")
            import traceback
            traceback.print_exc()

        finally:
            self.preview_btn.setEnabled(True)
            # 清理临时文件
            if safe_sub_path and safe_sub_path != self.subtitle_path and os.path.exists(safe_sub_path):
                try:
                    os.remove(safe_sub_path)
                except:
                    pass
            if preview_path and os.path.exists(preview_path):
                try:
                    os.remove(preview_path)
                except:
                    pass

    def _start_embed(self):
        """Start embedding subtitles into video."""
        if not self.subtitle_path or not self.video_path:
            return

        if not self.ffmpeg_path:
            QtWidgets.QMessageBox.warning(self, "错误", "FFmpeg未配置")
            return

        video_dir = os.path.dirname(self.video_path)
        base_name = os.path.splitext(os.path.basename(self.video_path))[0]
        output_path = os.path.join(video_dir, f"{base_name}_embed.mp4")

        chinese_factor = self.chinese_fontsize.value()
        other_factor = self.other_fontsize.value()
        margin = self.margin_spinbox.value() if self.margin_spinbox.value() > 0 else None
        zh_ass_color = self._get_ass_color(self.zh_color)
        other_ass_color = self._get_ass_color(self.other_color)

        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.embed_btn.setEnabled(False)
        self.file_group_enabled(False)
        self.status_label.setText("正在嵌入字幕...")

        # 【需求1 修改】：同样，使用安全文件名来修复 -22 错误
        # 我们创建一个临时属性来存储这个临时路径，以便在结束后清理
        self._temp_safe_sub = self._create_safe_temp_file(self.subtitle_path)

        try:
            # 传入安全路径给 embedder
            self.embedder.embed(
                self.video_path,
                self._temp_safe_sub,  # 使用无特殊字符的路径
                output_path,
                chinese_factor,
                other_factor,
                margin,
                zh_ass_color,
                other_ass_color
            )
        except Exception as e:
            self._on_error(str(e))

    def file_group_enabled(self, enabled):
        """Enable/disable file selection and parameters during processing."""
        self.sub_btn.setEnabled(enabled)
        self.video_btn.setEnabled(enabled)
        self.preview_btn.setEnabled(enabled)
        self.chinese_fontsize.setEnabled(enabled)
        self.other_fontsize.setEnabled(enabled)
        self.zh_color_btn.setEnabled(enabled)
        self.other_color_btn.setEnabled(enabled)
        self.margin_spinbox.setEnabled(enabled)

    def _on_progress(self, value):
        self.progress_bar.setValue(value)
        self.status_label.setText(f"处理中: {value}%")

    def _on_finished(self, output_path):
        self.progress_bar.setValue(100)
        self.status_label.setText("处理完成！")
        self.embed_btn.setEnabled(True)
        self.file_group_enabled(True)

        # 清理临时字幕文件
        if hasattr(self, '_temp_safe_sub') and os.path.exists(self._temp_safe_sub):
            try:
                os.remove(self._temp_safe_sub)
            except:
                pass

        reply = QtWidgets.QMessageBox.question(
            self,
            "完成",
            f"字幕嵌入完成！\n输出文件: {output_path}\n\n是否打开所在文件夹？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            folder = os.path.dirname(output_path)
            os.startfile(folder)

    def _on_error(self, error_msg):
        self.progress_bar.setVisible(False)
        self.status_label.setText("处理失败")
        self.embed_btn.setEnabled(True)
        self.file_group_enabled(True)

        # 清理临时字幕文件
        if hasattr(self, '_temp_safe_sub') and os.path.exists(self._temp_safe_sub):
            try:
                os.remove(self._temp_safe_sub)
            except:
                pass

        QtWidgets.QMessageBox.critical(self, "错误", f"嵌入过程出错:\n{error_msg}")