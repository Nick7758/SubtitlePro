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


def create_ass_style(subs: pysubs2.SSAFile, video_width: int, fontsize_factor: float = 0.045):
    """Create bilingual ASS styles based on video width."""
    fontsize = video_width * fontsize_factor
    outline = max(1, fontsize * 0.08)
    shadow = max(1, fontsize * 0.06)

    subs.styles["Default"].fontsize = fontsize
    subs.styles["Default"].shadow = shadow
    subs.styles["Default"].outline = outline

    subs.styles["Chinese"] = subs.styles["Default"].copy()
    subs.styles["Chinese"].fontsize = fontsize
    subs.styles["Chinese"].shadow = shadow
    subs.styles["Chinese"].outline = outline


def convert_srt_to_ass(video_path: str, srt_path: str, ass_path: str, ffmpeg_path: str, ffprobe_path: str):
    """Convert SRT subtitles to styled ASS format."""
    width, height = probe_video_size(video_path, ffprobe_path)

    subs = pysubs2.load(srt_path, encoding="utf-8")
    create_ass_style(subs, width)

    # Apply styles to events
    for line in subs.events:
        if "[zh]" in line.text:
            line.style = "Chinese"

    subs.styles["Default"].fontsize = width * 0.045
    subs.save(ass_path)


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

    def embed(self, video_path: str, srt_path: str, output_path: str):
        """Start embedding subtitles into video."""
        self._input_video = video_path
        self._output_video = output_path

        # Convert SRT to ASS
        ass_path = srt_path.replace(".srt", ".ass")
        convert_srt_to_ass(video_path, srt_path, ass_path, self.ffmpeg_path, self.ffprobe_path)

        # Prepare FFmpeg command
        drawbox_filter = "drawbox=y=ih-h:w=iw:h=ih/6:t=max:color=black@0.7"
        ass_filter = f"ass={ass_path.replace(os.sep, '/')}"
        filter_complex = f"{drawbox_filter},{ass_filter}"

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", video_path,
            "-vf", filter_complex,
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "veryfast",
            "-c:a", "copy",
            output_path
        ]

        self.proc.start(" ".join(cmd))

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