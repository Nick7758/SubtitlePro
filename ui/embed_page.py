from PyQt5 import QtCore, QtGui, QtWidgets
from core.workers import VideoDownloadWorker
from typing import Optional, List
import time
import os
from config.settings import ASR_DICT, TRANS_DICT, DOWNLOAD_VIDEO_DIR, SUB_RESULT_DIR, VIDEO_RESULT_DIR
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
from core.subtitle_processor import (
    SubtitleEmbedder,
    create_preview_frame,
    probe_video_size
)

class EmbedSubtitlesPage(QtWidgets.QWidget):
    """Embed subtitles into video with customizable styling and preview."""
    
    def __init__(self, ffmpeg_path: str = "", ffprobe_path: str = "", parent=None):
        super().__init__(parent)
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.subtitle_path = None
        self.video_path = None
        self.preview_image_path = None
        self.embedder = None
        self.setup_ui()
    
    def setup_ui(self):
        # Main layout
        layout = QtWidgets.QVBoxLayout(self)
        
        # File selection section
        file_group = QtWidgets.QGroupBox("文件选择")
        file_layout = QtWidgets.QVBoxLayout(file_group)
        
        # Subtitle file selection
        subtitle_layout = QtWidgets.QHBoxLayout()
        self.subtitle_input = QtWidgets.QLineEdit()
        self.subtitle_input.setPlaceholderText("请选择字幕文件...")
        self.subtitle_input.setReadOnly(True)
        self.subtitle_btn = QtWidgets.QPushButton("选择字幕文件")
        self.subtitle_btn.clicked.connect(self._select_subtitle_file)
        subtitle_layout.addWidget(self.subtitle_input)
        subtitle_layout.addWidget(self.subtitle_btn)
        
        # Video file selection
        video_layout = QtWidgets.QHBoxLayout()
        self.video_input = QtWidgets.QLineEdit()
        self.video_input.setPlaceholderText("请选择视频文件...")
        self.video_input.setReadOnly(True)
        self.video_btn = QtWidgets.QPushButton("选择视频文件")
        self.video_btn.clicked.connect(self._select_video_file)
        video_layout.addWidget(self.video_input)
        video_layout.addWidget(self.video_btn)
        
        file_layout.addLayout(subtitle_layout)
        file_layout.addLayout(video_layout)
        
        # Parameters section
        params_group = QtWidgets.QGroupBox("字幕参数")
        params_layout = QtWidgets.QFormLayout(params_group)
        
        # Chinese font size
        self.chinese_fontsize = QtWidgets.QDoubleSpinBox()
        self.chinese_fontsize.setRange(0.01, 0.20)
        self.chinese_fontsize.setSingleStep(0.005)
        self.chinese_fontsize.setValue(0.045)
        self.chinese_fontsize.setDecimals(3)
        self.chinese_fontsize.setSuffix(" (视频宽度的倍数)")
        self.chinese_fontsize.valueChanged.connect(self._on_param_changed)
        
        # Other language font size
        self.other_fontsize = QtWidgets.QDoubleSpinBox()
        self.other_fontsize.setRange(0.01, 0.20)
        self.other_fontsize.setSingleStep(0.005)
        self.other_fontsize.setValue(0.04)
        self.other_fontsize.setDecimals(3)
        self.other_fontsize.setSuffix(" (视频宽度的倍数)")
        self.other_fontsize.valueChanged.connect(self._on_param_changed)
        
        # Bottom margin
        self.margin_spinbox = QtWidgets.QSpinBox()
        self.margin_spinbox.setRange(0, 500)
        self.margin_spinbox.setSingleStep(10)
        self.margin_spinbox.setValue(0)  # 0 means auto-calculate
        self.margin_spinbox.setSpecialValueText("自动计算")
        self.margin_spinbox.setSuffix(" 像素")
        self.margin_spinbox.valueChanged.connect(self._on_param_changed)
        
        params_layout.addRow("中文字体大小:", self.chinese_fontsize)
        params_layout.addRow("其他语言字体大小:", self.other_fontsize)
        params_layout.addRow("距离视频底部:", self.margin_spinbox)
        
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
        self.preview_label.setScaledContents(False)
        
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
        layout.addStretch()
    
    def _select_subtitle_file(self):
        """Select subtitle file."""
        default_dir = SUB_RESULT_DIR if os.path.exists(SUB_RESULT_DIR) else os.path.expanduser("~")
        
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "选择字幕文件",
            default_dir,
            "字幕文件 (*.srt *.ass *.ssa *.vtt);;所有文件 (*.*)"
        )
        
        if file:
            self.subtitle_path = file
            self.subtitle_input.setText(file)
            self._check_ready()
    
    def _select_video_file(self):
        """Select video file."""
        default_dir = VIDEO_RESULT_DIR if os.path.exists(VIDEO_RESULT_DIR) else os.path.expanduser("~")
        
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "选择视频文件",
            default_dir,
            "视频文件 (*.mp4 *.avi *.mkv *.mov *.flv);;所有文件 (*.*)"
        )
        
        if file:
            self.video_path = file
            self.video_input.setText(file)
            self._check_ready()
    
    def _check_ready(self):
        """Check if files are selected and enable buttons."""
        ready = bool(self.subtitle_path and self.video_path)
        self.preview_btn.setEnabled(ready)
        self.embed_btn.setEnabled(ready)

    
    def _on_param_changed(self):
        """Called when parameters change - clear preview to indicate it needs regeneration."""
        if self.preview_image_path:
            self.preview_label.setText("参数已更改，请重新生成预览")
            self.preview_image_path = None
    
    def _generate_preview(self):
        """Generate preview with first subtitle on first frame."""
        if not self.subtitle_path or not self.video_path:
            return
        
        if not self.ffmpeg_path or not self.ffprobe_path:
            QtWidgets.QMessageBox.warning(
                self, 
                "FFmpeg未配置", 
                "FFmpeg路径未配置或不存在。\n\n请到【设置】页面配置正确的FFmpeg路径。"
            )
            return
        
        # Validate FFmpeg paths
        if not os.path.exists(self.ffmpeg_path):
            QtWidgets.QMessageBox.warning(
                self, 
                "FFmpeg不存在", 
                f"FFmpeg文件不存在：\n{self.ffmpeg_path}\n\n请到【设置】页面配置正确的FFmpeg路径。"
            )
            return
        
        if not os.path.exists(self.ffprobe_path):
            QtWidgets.QMessageBox.warning(
                self, 
                "FFprobe不存在", 
                f"FFprobe文件不存在：\n{self.ffprobe_path}\n\n请确保FFmpeg和FFprobe在同一目录下。"
            )
            return
        
        self.status_label.setText("正在生成预览...")
        self.preview_btn.setEnabled(False)
        QtWidgets.QApplication.processEvents()
        
        try:
            import tempfile
            # Create temp preview image
            temp_preview = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            preview_path = temp_preview.name
            temp_preview.close()
            
            # Get parameters
            chinese_factor = self.chinese_fontsize.value()
            other_factor = self.other_fontsize.value()
            margin = self.margin_spinbox.value() if self.margin_spinbox.value() > 0 else None
            
            # Generate preview
            success = create_preview_frame(
                self.video_path,
                self.subtitle_path,
                preview_path,
                self.ffmpeg_path,
                self.ffprobe_path,
                chinese_factor,
                other_factor,
                margin
            )
            
            if success:
                # Display preview
                pixmap = QtGui.QPixmap(preview_path)
                if not pixmap.isNull():
                    # Scale to fit preview label while maintaining aspect ratio
                    scaled_pixmap = pixmap.scaled(
                        self.preview_label.size(),
                        QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation
                    )
                    self.preview_label.setPixmap(scaled_pixmap)
                    self.preview_image_path = preview_path
                    self.status_label.setText("预览生成成功")
                else:
                    self.status_label.setText("预览图片加载失败")
            else:
                self.status_label.setText("预览生成失败")
                QtWidgets.QMessageBox.warning(self, "预览失败", "无法生成预览，请检查文件格式")
        
        except Exception as e:
            self.status_label.setText(f"预览错误: {str(e)}")
            QtWidgets.QMessageBox.critical(self, "错误", f"生成预览时出错:\n{str(e)}")
        
        finally:
            self.preview_btn.setEnabled(True)
    
    def _start_embed(self):
        """Start embedding subtitles into video."""
        if not self.subtitle_path or not self.video_path:
            return
        
        if not self.ffmpeg_path or not self.ffprobe_path:
            QtWidgets.QMessageBox.warning(
                self, 
                "FFmpeg未配置", 
                "FFmpeg路径未配置或不存在。\n\n请到【设置】页面配置正确的FFmpeg路径。"
            )
            return
        
        # Validate FFmpeg paths
        if not os.path.exists(self.ffmpeg_path):
            QtWidgets.QMessageBox.warning(
                self, 
                "FFmpeg不存在", 
                f"FFmpeg文件不存在：\n{self.ffmpeg_path}\n\n请到【设置】页面配置正确的FFmpeg路径。"
            )
            return
        
        # Generate output filename
        video_dir = os.path.dirname(self.video_path)
        video_name = os.path.splitext(os.path.basename(self.video_path))[0]
        output_path = os.path.join(video_dir, f"{video_name}_with_subs.mp4")
        
        # Ask user to confirm/change output path
        output_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "保存嵌入字幕的视频",
            output_path,
            "MP4 视频 (*.mp4)"
        )
        
        if not output_path:
            return
        
        # Get parameters
        chinese_factor = self.chinese_fontsize.value()
        other_factor = self.other_fontsize.value()
        margin = self.margin_spinbox.value() if self.margin_spinbox.value() > 0 else None
        
        # Disable UI
        self.embed_btn.setEnabled(False)
        self.preview_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("正在嵌入字幕...")
        
        # Create embedder
        self.embedder = SubtitleEmbedder(self.ffmpeg_path, self.ffprobe_path, self)
        self.embedder.progress.connect(self._on_embed_progress)
        self.embedder.finished.connect(self._on_embed_finished)
        self.embedder.error.connect(self._on_embed_error)
        
        # Start embedding
        self.embedder.embed(
            self.video_path,
            self.subtitle_path,
            output_path,
            chinese_factor,
            other_factor,
            margin
        )
    
    def _on_embed_progress(self, value):
        """Update progress bar."""
        self.progress_bar.setValue(value)
    
    def _on_embed_finished(self, output_path):
        """Handle embedding completion."""
        self.progress_bar.setValue(100)
        self.status_label.setText(f"嵌入完成！保存至: {os.path.basename(output_path)}")
        
        # Re-enable UI
        self.embed_btn.setEnabled(True)
        self.preview_btn.setEnabled(True)
        
        # Show success message
        reply = QtWidgets.QMessageBox.information(
            self,
            "嵌入成功",
            f"字幕已成功嵌入视频！\n保存位置: {output_path}\n\n是否打开文件所在文件夹？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            import subprocess
            subprocess.Popen(f'explorer /select,"{output_path}"')
    
    def _on_embed_error(self, error_msg):
        """Handle embedding error."""
        self.progress_bar.setVisible(False)
        self.status_label.setText("嵌入失败")
        self.embed_btn.setEnabled(True)
        self.preview_btn.setEnabled(True)
        
        QtWidgets.QMessageBox.critical(self, "嵌入失败", f"嵌入字幕时出错:\n{error_msg}")
    
    def update_ffmpeg_paths(self, ffmpeg_path: str, ffprobe_path: str):
        """Update FFmpeg paths when settings change."""
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
