import os
import re
import json
import subprocess
import pysubs2
from PyQt5 import QtCore


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


def create_ass_style(subs: pysubs2.SSAFile, video_width: int, video_height: int,
                     chinese_fontsize_factor: float = 0.045, 
                     other_fontsize_factor: float = 0.04,
                     margin_v: int = None):
    """Create bilingual ASS styles based on video width with customizable parameters."""
    chinese_fontsize = video_width * chinese_fontsize_factor
    other_fontsize = video_width * other_fontsize_factor
    outline = max(1, chinese_fontsize * 0.08)
    shadow = max(1, chinese_fontsize * 0.06)
    
    # Calculate margin if not provided
    if margin_v is None:
        margin_v = int(video_height / 6)

    subs.styles["Default"].fontsize = other_fontsize
    subs.styles["Default"].shadow = shadow
    subs.styles["Default"].outline = outline
    subs.styles["Default"].marginv = margin_v

    subs.styles["Chinese"] = subs.styles["Default"].copy()
    subs.styles["Chinese"].fontsize = chinese_fontsize
    subs.styles["Chinese"].shadow = shadow
    subs.styles["Chinese"].outline = outline
    subs.styles["Chinese"].marginv = margin_v


def convert_srt_to_ass(video_path: str, srt_path: str, ass_path: str, ffmpeg_path: str, ffprobe_path: str,
                       chinese_fontsize_factor: float = 0.045,
                       other_fontsize_factor: float = 0.04,
                       margin_v: int = None):
    """Convert SRT subtitles to styled ASS format with customizable parameters."""
    width, height = probe_video_size(video_path, ffprobe_path)

    subs = pysubs2.load(srt_path, encoding="utf-8")
    create_ass_style(subs, width, height, chinese_fontsize_factor, other_fontsize_factor, margin_v)

    # Apply styles to events
    for line in subs.events:
        if "[zh]" in line.text:
            line.style = "Chinese"

    subs.save(ass_path)


def create_preview_frame(video_path: str, subtitle_path: str, output_image: str,
                        ffmpeg_path: str, ffprobe_path: str,
                        chinese_fontsize_factor: float = 0.045,
                        other_fontsize_factor: float = 0.04,
                        margin_v: int = None) -> bool:
    """
    Extract first frame and render first subtitle for preview.
    Uses the same approach as SubtitleEmbedder for path handling.
    Returns True if successful.
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
        print(f"[INFO] Subtitle: {subtitle_path}")
        
        # Load subtitles and get first subtitle
        subs = pysubs2.load(subtitle_path, encoding="utf-8")
        if not subs.events:
            print("[ERROR] No subtitle events found")
            return False
        
        first_sub = subs.events[0]
        print(f"[INFO] First subtitle at {first_sub.start}ms: {first_sub.text[:50] if len(first_sub.text) > 50 else first_sub.text}")
        
        # Create temporary ASS file with only first subtitle
        preview_subs = pysubs2.SSAFile()
        preview_subs.styles = subs.styles.copy()
        
        # Get video dimensions
        width, height = probe_video_size(video_path, ffprobe_path)
        print(f"[INFO] Video size: {width}x{height}")
        
        # Create style with custom parameters
        create_ass_style(preview_subs, width, height, chinese_fontsize_factor, other_fontsize_factor, margin_v)
        
        # Add only first subtitle
        preview_event = first_sub.copy()
        # Detect if Chinese and apply style
        if "[zh]" in preview_event.text or any('\u4e00' <= c <= '\u9fff' for c in preview_event.text):
            preview_event.style = "Chinese"
        preview_subs.events.append(preview_event)
        
        # Save temporary ASS file in same directory as video (to avoid path issues)
        video_dir = os.path.dirname(video_path)
        temp_ass_name = f"_temp_preview_{os.getpid()}.ass"
        temp_ass_path = os.path.join(video_dir, temp_ass_name)
        preview_subs.save(temp_ass_path)
        print(f"[INFO] Temp ASS: {temp_ass_path}")
        
        # Extract frame at first subtitle timestamp
        timestamp = first_sub.start / 1000.0  # Convert ms to seconds
        
        # Build FFmpeg command - use relative path to avoid Windows path issues
        # Since we set working dir to video_dir, we can just use the filename
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
        print(f"[INFO] WorkDir: {video_dir}")
        
        # Run using QProcess
        from PyQt5.QtCore import QProcess, QEventLoop
        
        proc = QProcess()
        proc.setWorkingDirectory(video_dir)  # Set CWD to avoid path issues
        proc.start(ffmpeg_path, args)
        
        # Wait for process to finish (blocking with event loop)
        loop = QEventLoop()
        proc.finished.connect(loop.quit)
        
        # Set timeout of 30 seconds
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
              margin_v: int = None):
        """Start embedding subtitles into video with custom parameters."""
        self._input_video = video_path
        self._output_video = output_path

        # Convert SRT to ASS with custom parameters
        ass_path = srt_path.replace(".srt", ".ass")
        convert_srt_to_ass(video_path, srt_path, ass_path, self.ffmpeg_path, self.ffprobe_path,
                          chinese_fontsize_factor, other_fontsize_factor, margin_v)

        # Prepare FFmpeg command
        # Use relative path for ASS file if possible, or fall back to absolute path with careful escaping
        # The best way is to set working directory to where the ASS file is
        ass_dir = os.path.dirname(ass_path)
        ass_name = os.path.basename(ass_path)
        
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