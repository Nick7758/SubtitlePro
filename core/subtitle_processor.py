import os
import re
import json
import subprocess
import pysubs2
from PyQt5 import QtCore

# Regex for Chinese characters
CN_RE = re.compile(r"[\u4e00-\u9fff]")


def probe_video_size(video_path: str, ffprobe_path: str) -> tuple[int, int]:
    """Probe video dimensions using ffprobe."""
    cmd = [
        ffprobe_path,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        video_path
    ]
    try:
        # Prevent console window on Windows
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        result = subprocess.run(cmd, capture_output=True, text=True, check=True, startupinfo=startupinfo)
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        return stream["width"], stream["height"]
    except Exception:
        return 1920, 1080  # fallback


def create_ass_style(subs: pysubs2.SSAFile, video_height: int, margin_v: int = None):
    """
    Create basic ASS styles.
    Note: Font sizes will be overridden by inline tags for bilingual support.
    """
    # Default base size (will be overridden)
    base_fontsize = int(video_height * 0.04)
    # Match main.py explicit thin outline/shadow style
    outline = 2.2
    shadow = 1.7

    # Calculate margin if not provided
    if margin_v is None:
        margin_v = int(video_height * 0.1)  # Default 10% from bottom

    # Base "Default" style
    subs.styles["Default"].fontsize = base_fontsize
    subs.styles["Default"].shadow = shadow
    subs.styles["Default"].outline = outline
    subs.styles["Default"].marginv = margin_v
    subs.styles["Default"].alignment = 2  # Bottom Center


def process_bilingual_event(event, video_height,
                            chinese_fontsize_factor, other_fontsize_factor,
                            chinese_color="&H00C3FF", other_color="&H00FFFFFF"):
    """
    Process a subtitle event to apply bilingual styling with inline tags.
    This separates styling for Chinese and other languages within the same event.
    """
    # Clean existing tags
    clean_text = re.sub(r"\{.*?\}", "", event.text)
    # Split by commonly used newline characters in subtitles
    lines = re.split(r"\\[Nn]|\n", clean_text.strip())

    en_fs = int(video_height * other_fontsize_factor)
    zh_fs = int(video_height * chinese_fontsize_factor)

    # Fonts (matching main.py style)
    ZH_FAM = "Microsoft YaHei"
    EN_FAM = "Arial"

    if len(lines) >= 2:
        # Detect language for each line to apply correct colors
        is_cn_0 = bool(CN_RE.search(lines[0]))
        is_cn_1 = bool(CN_RE.search(lines[1]))

        # Format each line based on its detected language
        def format_line(text, is_chinese):
            fam = ZH_FAM if is_chinese else EN_FAM
            fs = zh_fs if is_chinese else en_fs
            color = chinese_color if is_chinese else other_color
            bold = r"\b1" if is_chinese else r"\b0"
            return fr"{{\fn{fam}\fs{fs}{bold}\c{color}}}{text}"

        line0 = format_line(lines[0], is_cn_0)
        line1 = format_line(lines[1], is_cn_1)
        event.text = line0 + r"\N" + line1
    elif len(lines) == 1:
        # Single line: detect language
        is_cn = bool(CN_RE.search(lines[0]))

        fam = ZH_FAM if is_cn else EN_FAM
        fs = zh_fs if is_cn else en_fs
        color = chinese_color if is_cn else other_color
        bold = r"\b1"  # Bold for single line

        event.text = fr"{{\fn{fam}\fs{fs}{bold}\c{color}}}{lines[0]}"

    return event


def convert_srt_to_ass(video_path: str, srt_path: str, ass_path: str, ffmpeg_path: str, ffprobe_path: str,
                       chinese_fontsize_factor: float = 0.045,
                       other_fontsize_factor: float = 0.04,
                       margin_v: int = None,
                       chinese_color: str = "&H00C3FF",
                       other_color: str = "&H00FFFFFF"):
    """Convert SRT subtitles to styled ASS format with independent bilingual sizing."""
    width, height = probe_video_size(video_path, ffprobe_path)

    # Try to load with utf-8, fallback if needed
    try:
        subs = pysubs2.load(srt_path, encoding="utf-8")
    except UnicodeDecodeError:
        try:
            subs = pysubs2.load(srt_path, encoding="gbk")
        except:
            subs = pysubs2.load(srt_path)

    # Setup base styles
    create_ass_style(subs, height, margin_v)

    # Apply inline styles to all events
    for line in subs.events:
        process_bilingual_event(line, height, chinese_fontsize_factor, other_fontsize_factor, chinese_color,
                                other_color)

    subs.save(ass_path)


def create_preview_frame(video_path: str, subtitle_path: str, output_image: str,
                         ffmpeg_path: str, ffprobe_path: str,
                         chinese_fontsize_factor: float = 0.045,
                         other_fontsize_factor: float = 0.04,
                         margin_v: int = None,
                         chinese_color: str = "&H00C3FF",
                         other_color: str = "&H00FFFFFF") -> bool:
    """
    Extract first frame and render first subtitle for preview.
    Uses relative paths to avoid Windows path escaping issues.
    """
    try:
        # Validate inputs
        if not os.path.exists(ffmpeg_path):
            print(f"[ERROR] FFmpeg not found: {ffmpeg_path}")
            return False

        if not os.path.exists(video_path):
            print(f"[ERROR] Video not found: {video_path}")
            return False

        if not os.path.exists(subtitle_path):
            print(f"[ERROR] Subtitle not found: {subtitle_path}")
            return False

        # Load subtitles
        try:
            subs = pysubs2.load(subtitle_path, encoding="utf-8")
        except UnicodeDecodeError:
            subs = pysubs2.load(subtitle_path)

        if not subs.events:
            print("[ERROR] No subtitle events found")
            return False

        # Get video dimensions
        width, height = probe_video_size(video_path, ffprobe_path)

        # Find first event and its timestamp
        first_sub = subs.events[0]
        # Calculate the real timestamp to seek to in the video
        seek_timestamp = first_sub.start / 1000.0

        # Create temporary ASS file
        preview_subs = pysubs2.SSAFile()
        preview_subs.styles = subs.styles.copy()

        # Setup base styles
        create_ass_style(preview_subs, height, margin_v)

        # Add first subtitle and apply bilingual styling
        preview_event = first_sub.copy()

        # --- 【关键修复】 ---
        # 强制将预览字幕的开始时间设为 0
        # 因为 FFmpeg 使用 -ss 在输入前跳转时，会重置视频时间戳为 0
        # 如果不把字幕时间也改为 0，字幕就会显示在很久以后，导致当前画面无字幕
        preview_event.start = 0
        preview_event.end = 5000  # 给它 5 秒的持续时间，保证能显示

        process_bilingual_event(preview_event, height, chinese_fontsize_factor, other_fontsize_factor, chinese_color,
                                other_color)
        preview_subs.events.append(preview_event)

        # Save temporary ASS file in same directory as video (to avoid path issues)
        video_dir = os.path.dirname(os.path.abspath(video_path))
        temp_ass_name = f"_temp_preview_{os.getpid()}.ass"
        temp_ass_path = os.path.join(video_dir, temp_ass_name)
        preview_subs.save(temp_ass_path)

        # Build FFmpeg command
        # Use relative path for ASS file
        ass_filter = f"ass='{temp_ass_name}'"

        # Build args list
        args = [
            "-y",
            "-ss", str(seek_timestamp),  # Jump video to the original subtitle time
            "-i", video_path,
            "-vf", ass_filter,  # Apply the modified subtitle (which starts at 0)
            "-frames:v", "1",
            output_image
        ]

        # Run using QProcess
        from PyQt5.QtCore import QProcess, QEventLoop

        proc = QProcess()
        proc.setWorkingDirectory(video_dir)  # Set CWD to avoid path issues
        proc.start(ffmpeg_path, args)

        # Wait for process to finish
        loop = QEventLoop()
        proc.finished.connect(loop.quit)

        # Timeout
        from PyQt5.QtCore import QTimer
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(30000)

        loop.exec_()
        timer.stop()

        # Clean up temp file
        try:
            if os.path.exists(temp_ass_path):
                os.remove(temp_ass_path)
        except:
            pass

        # Check result
        if not os.path.exists(output_image) or os.path.getsize(output_image) == 0:
            return False

        return True

    except Exception as e:
        import traceback
        print(f"[ERROR] Preview generation exception: {e}")
        print(traceback.format_exc())
        return False


class SubtitleEmbedder(QtCore.QObject):
    """Handles subtitle embedding using FFmpeg."""
    progress = QtCore.pyqtSignal(int)
    finished = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)

    def __init__(self, ffmpeg_path: str, ffprobe_path: str, parent=None):
        super().__init__(parent)
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.proc = QtCore.QProcess(self)
        self.proc.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._on_output)
        self.proc.finished.connect(self._on_finished)
        self._input_video = ""
        self._output_video = ""
        self._temp_ass_path = ""  # Keep track of temp file
        self._retry_mode = False

    def embed(self, video_path: str, srt_path: str, output_path: str,
              chinese_fontsize_factor: float = 0.045,
              other_fontsize_factor: float = 0.04,
              margin_v: int = None,
              chinese_color: str = "&H00C3FF",
              other_color: str = "&H00FFFFFF"):
        """Start embedding subtitles into video with custom parameters."""
        self._input_video = video_path
        self._output_video = output_path

        # Save original params for retry
        self._original_srt_path = srt_path
        self._chinese_fontsize_factor = chinese_fontsize_factor
        self._other_fontsize_factor = other_fontsize_factor
        self._margin_v = margin_v
        self._chinese_color = chinese_color
        self._other_color = other_color

        # Reset retry mode
        self._retry_mode = False

        # Generate ASS file path in same directory as video
        video_dir = os.path.dirname(os.path.abspath(video_path))
        # Use a hidden temp name to avoid cluttering user view
        ass_filename = f".temp_embed_{os.path.splitext(os.path.basename(srt_path))[0]}.ass"
        self._temp_ass_path = os.path.join(video_dir, ass_filename)

        print(f"[DEBUG] Converting SRT to ASS: {self._temp_ass_path}")

        # Convert SRT to ASS
        try:
            convert_srt_to_ass(video_path, srt_path, self._temp_ass_path, self.ffmpeg_path, self.ffprobe_path,
                               chinese_fontsize_factor, other_fontsize_factor, margin_v,
                               chinese_color, other_color)
        except Exception as e:
            self.error.emit(f"字幕格式转换失败: {str(e)}")
            return

        # Prepare FFmpeg command
        video_abs = os.path.abspath(video_path).replace("\\", "/")
        output_abs = os.path.abspath(output_path).replace("\\", "/")

        # Ensure output != input
        if video_abs.lower() == output_abs.lower():
            base, ext = os.path.splitext(output_abs)
            output_abs = f"{base}_new{ext}"
            self._output_video = output_abs

        # Use relative path for ASS filename
        ass_filter = f"ass='{ass_filename}'"
        vf_combined = ass_filter

        # Add -sn to disable copying internal subtitles
        args = [
            "-y",
            "-i", video_abs,
            "-vf", vf_combined,
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "veryfast",
            "-c:a", "copy",
            "-sn",  # Disable subtitle stream copying
            output_abs
        ]

        print(f"[DEBUG] Command: {self.ffmpeg_path} {' '.join(args)}")

        # Set working directory to video dir so FFmpeg finds the relative ASS file
        self.proc.setWorkingDirectory(video_dir)
        self.proc.start(self.ffmpeg_path, args)

    def _on_output(self):
        """Parse FFmpeg output for progress."""
        output = self.proc.readAllStandardOutput().data().decode("utf-8", errors="ignore")

        # Try to parse duration if not set
        if not hasattr(self, '_duration_sec') or self._duration_sec == 0:
            duration_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", output)
            if duration_match:
                h, m, s = map(float, duration_match.groups())
                self._duration_sec = h * 3600 + m * 60 + s

        time_match = re.search(r"time=(\d{2}):(\d{2}):(\d{2}\.\d{2})", output)
        if time_match and hasattr(self, '_duration_sec') and self._duration_sec > 0:
            h, m, s = map(float, time_match.groups())
            current_sec = h * 3600 + m * 60 + s
            progress = int((current_sec / self._duration_sec) * 100)
            self.progress.emit(min(progress, 99))

    def _on_finished(self, code, _status):
        """Handle process completion."""
        print(f"[DEBUG] FFmpeg finished with code: {code}")

        # Cleanup temp files immediately
        self._cleanup_temp_files()

        output_exists = os.path.exists(self._output_video)
        output_size = 0
        if output_exists:
            output_size = os.path.getsize(self._output_video)

        # Success condition
        if (code == 0 or code == -22) and output_exists and output_size > 0:
            self.progress.emit(100)
            self.finished.emit(self._output_video)
        elif not self._retry_mode and output_size == 0:
            # Retry logic (if needed)
            print(f"[WARNING] Processing failed, attempting retry...")
            self._retry_mode = True
            self.error.emit(f"处理失败，生成的视频为空 (Code: {code})")
        else:
            # Failure
            if output_exists and output_size == 0:
                try:
                    os.remove(self._output_video)
                except:
                    pass

            self.error.emit(f"FFmpeg 处理失败 (退出码: {code})")

    def _cleanup_temp_files(self):
        """Remove temporary ASS files."""
        if self._temp_ass_path and os.path.exists(self._temp_ass_path):
            try:
                os.remove(self._temp_ass_path)
                print(f"[DEBUG] Cleaned up temp file: {self._temp_ass_path}")
            except Exception as e:
                print(f"[WARNING] Failed to cleanup temp file: {e}")