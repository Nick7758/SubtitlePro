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
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
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
        margin_v = int(video_height * 0.1) # Default 10% from bottom

    # Base "Default" style
    subs.styles["Default"].fontsize = base_fontsize
    subs.styles["Default"].shadow = shadow
    subs.styles["Default"].outline = outline
    subs.styles["Default"].marginv = margin_v
    subs.styles["Default"].alignment = 2 # Bottom Center


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
        bold = r"\b1" # Bold for single line
        
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

    subs = pysubs2.load(srt_path, encoding="utf-8")
    
    # Setup base styles
    create_ass_style(subs, height, margin_v)

    # Apply inline styles to all events
    for line in subs.events:
        process_bilingual_event(line, height, chinese_fontsize_factor, other_fontsize_factor, chinese_color, other_color)

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
        
        print(f"[INFO] Using FFmpeg: {ffmpeg_path}")
        print(f"[INFO] Video: {video_path}")
        
        # Load subtitles and get first subtitle
        subs = pysubs2.load(subtitle_path, encoding="utf-8")
        if not subs.events:
            print("[ERROR] No subtitle events found")
            return False
        
        # Get video dimensions
        width, height = probe_video_size(video_path, ffprobe_path)
        print(f"[INFO] Video size: {width}x{height}")
        
        first_sub = subs.events[0]
        
        # Create temporary ASS file
        preview_subs = pysubs2.SSAFile()
        preview_subs.styles = subs.styles.copy()
        
        # Setup base styles
        create_ass_style(preview_subs, height, margin_v)
        
        # Add first subtitle and apply bilingual styling
        preview_event = first_sub.copy()
        process_bilingual_event(preview_event, height, chinese_fontsize_factor, other_fontsize_factor, chinese_color, other_color)
        preview_subs.events.append(preview_event)
        
        # Save temporary ASS file in same directory as video (to avoid path issues)
        video_dir = os.path.dirname(video_path)
        temp_ass_name = f"_temp_preview_{os.getpid()}.ass"
        temp_ass_path = os.path.join(video_dir, temp_ass_name)
        preview_subs.save(temp_ass_path)
        print(f"[INFO] Temp ASS: {temp_ass_path}")
        
        # Extract frame at first subtitle timestamp
        timestamp = first_sub.start / 1000.0  # Convert ms to seconds
        
        # Build FFmpeg command
        # Use relative path for ASS file
        ass_filter = f"ass='{temp_ass_name}'"
        
        # Build args list
        args = [
            "-y",
            "-ss", str(timestamp),
            "-i", video_path,
            "-vf", ass_filter,
            "-frames:v", "1",
            output_image
        ]
        
        print(f"[INFO] Command: {ffmpeg_path} {' '.join(args)}")
        
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
        
        exit_code = proc.exitCode()
        if exit_code != 0:
            stderr = bytes(proc.readAllStandardError()).decode('utf-8', errors='ignore')
            print(f"[ERROR] FFmpeg failed with code {exit_code}")
            print(f"[ERROR] STDERR: {stderr}")
        
        # Clean up temp file
        try:
            os.remove(temp_ass_path)
        except:
            pass
        
        # Check result
        if not os.path.exists(output_image):
            print(f"[ERROR] Output image not created: {output_image}")
            return False
        
        print(f"[SUCCESS] Preview generated: {output_image}")
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

    def embed(self, video_path: str, srt_path: str, output_path: str,
              chinese_fontsize_factor: float = 0.045,
              other_fontsize_factor: float = 0.04,
              margin_v: int = None,
              chinese_color: str = "&H00C3FF",
              other_color: str = "&H00FFFFFF"):
        """Start embedding subtitles into video with custom parameters."""
        self._input_video = video_path
        self._output_video = output_path

        # Convert SRT to ASS with custom parameters (and styling)
        ass_path = srt_path.replace(".srt", ".ass")
        convert_srt_to_ass(video_path, srt_path, ass_path, self.ffmpeg_path, self.ffprobe_path,
                          chinese_fontsize_factor, other_fontsize_factor, margin_v,
                          chinese_color, other_color)

        # Prepare FFmpeg command
        ass_dir = os.path.dirname(ass_path)
        ass_name = os.path.basename(ass_path)
        
        # Use simpler drawbox if needed or match main.py style
        drawbox_filter = "drawbox=y=ih-h:w=iw:h=ih/6:t=max:color=black@0.7"
        ass_filter = f"ass='{ass_name}'"
        filter_complex = f"{drawbox_filter},{ass_filter}"

        cmd = [
            "-y",
            "-i", video_path,
            "-vf", filter_complex,
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "veryfast",
            "-c:a", "copy",
            output_path
        ]
        
        self.proc.setWorkingDirectory(ass_dir)
        self.proc.start(self.ffmpeg_path, cmd)

    def _on_output(self):
        """Parse FFmpeg output for progress."""
        output = self.proc.readAllStandardOutput().data().decode("utf-8", errors="ignore")
        duration_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", output)
        time_match = re.search(r"time=(\d{2}):(\d{2}):(\d{2}\.\d{2})", output)

        if duration_match and time_match:
            h, m, s = map(float, duration_match.groups())
            duration_sec = h * 3600 + m * 60 + s

            h, m, s = map(float, time_match.groups())
            current_sec = h * 3600 + m * 60 + s

            progress = int((current_sec / duration_sec) * 100)
            self.progress.emit(min(progress, 99))

    def _on_finished(self, code, _status):
        """Handle process completion."""
        if code == 0 and os.path.exists(self._output_video):
            self.progress.emit(100)
            self.finished.emit(self._output_video)
        else:
            self.error.emit(f"FFmpeg 处理失败 (退出码: {code})")