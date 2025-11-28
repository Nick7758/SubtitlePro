import os
import sys
import time
import subprocess
import yt_dlp
from PyQt5 import QtCore
from config.settings import WORK_DIR

class FFmpegAudioWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(str, str)
    error = QtCore.pyqtSignal(str, str)
    progress = QtCore.pyqtSignal(int)

    def __init__(self, ffmpeg_path: str, parent=None):
        super().__init__(parent)
        self.ffmpeg_path = ffmpeg_path
        self.proc = QtCore.QProcess(self)
        self.proc.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._on_output)
        self.proc.finished.connect(self._on_finished)
        self._video = None
        self._audio = None

    def extract(self, video_path: str, audio_path: str):
        self._video = video_path
        self._audio = audio_path
        
        # 检查FFmpeg路径是否存在
        if not os.path.exists(self.ffmpeg_path):
            self.error.emit(self._video or "", f"FFmpeg未找到: {self.ffmpeg_path}")
            return
            
        # 检查视频文件是否存在
        if not os.path.exists(video_path):
            self.error.emit(self._video or "", f"视频文件不存在: {video_path}")
            return
            
        # 确保输出目录存在
        audio_dir = os.path.dirname(audio_path)
        if not os.path.exists(audio_dir):
            try:
                os.makedirs(audio_dir, exist_ok=True)
            except Exception as e:
                self.error.emit(self._video or "", f"无法创建音频目录: {audio_dir} ({str(e)})")
                return
                
        # 尝试删除已存在的音频文件
        try:
            if os.path.exists(audio_path): 
                os.remove(audio_path)
        except Exception as e:
            self.error.emit(self._video or "", f"无法删除现有音频文件: {audio_path} ({str(e)})")
            return
            
        args = ["-y", "-i", video_path, "-vn", "-acodec", "aac", "-ar", "16000", "-ac", "1", audio_path]
        self.proc.start(self.ffmpeg_path, args)

    def _on_output(self):
        self.progress.emit(int((time.time() * 10) % 99))

    def _on_finished(self, code, _status):
        if code == 0 and os.path.exists(self._audio or ""):
            self.progress.emit(100)
            self.finished.emit(self._video or "", self._audio or "")
        else:
            # 提供更详细的错误信息
            error_msg = f"FFmpeg执行失败，退出码: {code}"
            if code == -2:
                error_msg += " (可能是权限问题或文件路径错误)"
            elif code == 1:
                error_msg += " (通用错误)"
            elif code == 2:
                error_msg += " (参数错误)"
            self.error.emit(self._video or "", error_msg)

class CookieGeneratorWorker(QtCore.QThread):
    """
    Multi-Browser Cookie Extractor (Supports Chrome, Edge, Firefox, Brave, Opera).
    """
    finished = QtCore.pyqtSignal(bool, str)
    log = QtCore.pyqtSignal(str)

    def run(self):
        target_file = os.path.join(WORK_DIR, "cookies.txt")

        # Updated List of browsers to try
        # Format: (yt-dlp_internal_name, windows_exe_name, display_name)
        browsers = [
            ("chrome", "chrome.exe", "Google Chrome"),
            ("edge", "msedge.exe", "Microsoft Edge"),
            ("brave", "brave.exe", "Brave Browser"),
            ("firefox", "firefox.exe", "Mozilla Firefox"),
            ("opera", "opera.exe", "Opera"),
            ("vivaldi", "vivaldi.exe", "Vivaldi")
        ]

        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        success_browser = None
        errors = []

        for b_id, b_exe, b_name in browsers:
            self.log.emit(f"正在尝试从 {b_name} 同步...")

            # 1. Force kill the browser to release the SQLite DB lock
            # Chrome/Edge are very strict about file locking; this is necessary.
            try:
                subprocess.run(["taskkill", "/F", "/IM", b_exe],
                               check=False, startupinfo=si, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(1.5)  # Give OS time to release the file handle
            except Exception:
                pass

            # 2. Run yt-dlp extraction
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "--cookies-from-browser", b_id,
                "--cookies", target_file,
                "--skip-download",
                "https://www.youtube.com"
            ]

            try:
                # We capture output to check for specific success/fail messages
                res = subprocess.run(cmd, capture_output=True, text=True, startupinfo=si)

                # Check if file created and has content
                if os.path.exists(target_file) and os.path.getsize(target_file) > 0:
                    # Validation: Ensure it actually grabbed YouTube/Google cookies
                    with open(target_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        if ".youtube.com" in content or "google.com" in content:
                            success_browser = b_name
                            break  # SUCCESS! Stop iterating.

                # Logging specific errors for debugging
                err_msg = res.stderr.strip()
                if not err_msg:
                    # Sometimes yt-dlp fails silently if the DB is encrypted with a key it can't get
                    err_msg = "提取失败 (可能是未登录或无法解密)"

                errors.append(f"[{b_name}] {err_msg[:80]}...")

            except Exception as e:
                errors.append(f"[{b_name}] 异常: {str(e)}")

        if success_browser:
            self.finished.emit(True, f"成功从 {success_browser} 同步登录信息！")
        else:
            detail = "\n".join(errors)
            self.finished.emit(False,
                               f"同步失败。\n请确保您在 Chrome/Edge/Firefox 上已登录 YouTube。\n注意：程序必须关闭浏览器才能读取数据。\n\n调试信息:\n{detail}")

class VideoDownloadWorker(QtCore.QThread):
    """Runs yt-dlp in a background thread with Audio/Video merge protection."""
    progress = QtCore.pyqtSignal(int)
    log = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)

    def __init__(self, url: str, output_dir: str, ffmpeg_path: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.output_dir = output_dir
        self.ffmpeg_path = ffmpeg_path

    def run(self):
        # 1. Check if FFmpeg actually exists at the path
        ffmpeg_exists = os.path.exists(self.ffmpeg_path) and os.path.isfile(self.ffmpeg_path)
        ffmpeg_dir = os.path.dirname(self.ffmpeg_path) if ffmpeg_exists else None

        if not ffmpeg_exists:
            self.log.emit("⚠️ 警告：未检测到 FFmpeg，将仅下载 720p (以确保有声音)...")

        # 2. Configure Options
        ydl_opts = {
            'outtmpl': os.path.join(self.output_dir, '%(title)s.%(ext)s'),
            'noplaylist': True,
            'progress_hooks': [self._progress_hook],
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
        }

        # 3. Smart Format Selection
        if ffmpeg_exists:
            # If FFmpeg is found, download Best Video + Best Audio and merge them
            ydl_opts['ffmpeg_location'] = ffmpeg_dir
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
            ydl_opts['merge_output_format'] = 'mp4'
        else:
            # If FFmpeg is MISSING, download the "best single file" (usually 720p)
            # This guarantees audio and video are in one file, avoiding silence.
            ydl_opts['format'] = 'best[ext=mp4]/best'

        # 4. Cookie handling
        cookie_txt = os.path.join(WORK_DIR, "cookies.txt")
        using_cookie = False
        if os.path.exists(cookie_txt) and os.path.getsize(cookie_txt) > 0:
            self.log.emit("使用已同步的登录凭证...")
            ydl_opts['cookiefile'] = cookie_txt
            using_cookie = True

        try:
            self.log.emit(f"正在解析: {self.url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                if info:
                    filename = ydl.prepare_filename(info)
                    # If merged, update extension to mp4
                    if ffmpeg_exists and ydl_opts.get('merge_output_format'):
                        base, _ = os.path.splitext(filename)
                        filename = base + "." + ydl_opts['merge_output_format']

                    self.progress.emit(100)
                    self.finished.emit(filename)
                else:
                    raise Exception("无法获取视频信息")

        except Exception as e:
            err_str = str(e)
            if "cookie" in err_str.lower() or "sign in" in err_str.lower() or "403" in err_str:
                if using_cookie:
                    self.error.emit(f"下载被拒绝：Cookie 可能已失效。\n请删除旧 Cookie 并重新同步。\n(原始错误: {err_str[:50]}...)")
                else:
                    self.error.emit("下载失败：需要登录。\n请点击【一键同步】按钮。")
            else:
                self.error.emit(f"下载出错: {err_str}")

    def _progress_hook(self, d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            if total:
                self.progress.emit(int(d.get('downloaded_bytes', 0) / total * 100))
        elif d['status'] == 'finished':
            self.log.emit("下载完成，正在处理...")