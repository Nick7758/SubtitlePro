import os
import re
import json
import subprocess
import pysubs2
from PyQt5 import QtCore

# 正则表达式：用于匹配中文字符及全角标点
CN_RE = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")


def get_text_weight(text):
    """辅助函数：计算文本的视觉权重（长度得分），用于挑选最长字幕"""
    if not text: return 0
    clean_text = re.sub(r"\{.*?\}", "", text).strip()
    return sum(2 if CN_RE.search(char) or ord(char) > 127 else 1 for char in clean_text)


# def smart_wrap_text(text, fontsize_factor, is_portrait=True):
#     r"""
#     智能换行算法（单词感知版）：
#     针对英文按空格拆分填满一行；针对中文按字符强制断行。
#     """
#     if not text or not fontsize_factor:
#         return text
#
#     # 使用你调整后的参数
#     coeff = 0.52 if is_portrait else 1.32
#     max_units = int(coeff / fontsize_factor)
#
#     if ' ' in text.strip():
#         words = text.split(' ')
#         lines = []
#         current_line_words = []
#         current_units = 0
#
#         for word in words:
#             if not word: continue
#             word_w = get_text_weight(word)
#             space_w = 1 if current_line_words else 0
#
#             if current_units + word_w + space_w <= max_units:
#                 current_line_words.append(word)
#                 current_units += (word_w + space_w)
#             else:
#                 if current_line_words:
#                     lines.append(" ".join(current_line_words))
#                 current_line_words = [word]
#                 current_units = word_w
#
#         if current_line_words:
#             lines.append(" ".join(current_line_words))
#         return r"\N".join(lines)
#     else:
#         lines = []
#         current_line = ""
#         current_units = 0
#         for char in text:
#             weight = 2 if CN_RE.search(char) or ord(char) > 127 else 1
#             if current_units + weight > max_units and current_line:
#                 lines.append(current_line)
#                 current_line = char
#                 current_units = weight
#             else:
#                 current_line += char
#                 current_units += weight
#         if current_line: lines.append(current_line)
#         return r"\N".join(lines)

def smart_wrap_text(text, fontsize_factor, is_portrait=True):
    r"""
    智能换行算法（定制版）：
    1. 针对中文部分：执行字符级智能换行，严格控制宽度，防止溢出。
    2. 针对英文/外语部分：原样返回，不人工插入 \N，完全交给 FFmpeg 默认逻辑处理。
    """
    if not text or not fontsize_factor:
        return text

    # --- 核心修改：语言判定 ---
    # 如果该段文本不包含任何中文字符，则直接返回原文本，不干预其换行
    if not CN_RE.search(text):
        return text

    # --- 中文逻辑处理部分（完全保留你之前的调优参数） ---
    # 竖屏系数 0.52，横屏系数 1.32
    coeff = 0.52 if is_portrait else 1.32
    max_units = int(coeff / fontsize_factor)

    lines = []
    current_line = ""
    current_units = 0

    for char in text:
        # 判断字符权重：中文或全角符号权重为 2，其余（如数字、半角标点）权重为 1
        weight = 2 if CN_RE.search(char) or ord(char) > 127 else 1

        if current_units + weight > max_units and current_line:
            # 达到行宽上限，存入当前行并开启新行
            lines.append(current_line)
            current_line = char
            current_units = weight
        else:
            current_line += char
            current_units += weight

    if current_line:
        lines.append(current_line)

    return r"\N".join(lines)

def probe_video_info(video_path: str, ffprobe_path: str) -> tuple[int, int, float]:
    """获取视频的分辨率和总时长."""
    cmd = [
        ffprobe_path, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration", "-of", "json", video_path
    ]
    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, startupinfo=startupinfo)
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        w = int(stream.get("width", 1920))
        h = int(stream.get("height", 1080))
        d = float(stream.get("duration", 0.0))
        return w, h, d
    except Exception:
        return 1920, 1080, 0.0


def probe_video_size(video_path: str, ffprobe_path: str) -> tuple[int, int]:
    """兼容旧接口的别名函数."""
    w, h, _ = probe_video_info(video_path, ffprobe_path)
    return w, h


def process_bilingual_event(event, video_height, is_portrait,
                            chinese_fontsize_factor, other_fontsize_factor,
                            chinese_color="&H00C3FF", other_color="&H00FFFFFF"):
    r"""处理单个字幕行的样式和换行."""
    clean_text = re.sub(r"\{.*?\}", "", event.text)
    original_lines = re.split(r"\\[Nn]|\n", clean_text.strip())

    zh_fs = int(video_height * chinese_fontsize_factor)
    en_fs = int(video_height * other_fontsize_factor)
    ZH_FAM, EN_FAM = "Microsoft YaHei", "Arial"

    final_processed_lines = []
    for raw_line in original_lines:
        if not raw_line.strip(): continue
        is_cn = bool(CN_RE.search(raw_line))
        factor = chinese_fontsize_factor if is_cn else other_fontsize_factor
        fam = ZH_FAM if is_cn else EN_FAM
        fs = zh_fs if is_cn else en_fs
        color = chinese_color if is_cn else other_color
        bold = r"\b1" if is_cn else r"\b0"

        wrapped_text = smart_wrap_text(raw_line, factor, is_portrait)
        styled_line = fr"{{\fn{fam}\fs{fs}{bold}\c{color}}}{wrapped_text}"
        final_processed_lines.append(styled_line)

    event.text = r"\N".join(final_processed_lines)
    return event


def convert_srt_to_ass(video_path, srt_path, ass_path, ffmpeg_path, ffprobe_path,
                       zh_factor, en_factor, margin_v, zh_color, en_color):
    """正式嵌入转换函数."""
    width, height, _ = probe_video_info(video_path, ffprobe_path)
    is_portrait = height > width

    try:
        subs = pysubs2.load(srt_path, encoding="utf-8")
    except:
        subs = pysubs2.load(srt_path)

    # 启用填满一行模式
    subs.info["WrapStyle"] = "1"

    # 设置样式属性
    style = subs.styles["Default"]
    style.fontsize = int(height * 0.04)
    style.marginv = margin_v if margin_v is not None else int(height * 0.1)
    style.alignment = 2  # 底部居中
    style.outline = 2
    style.shadow = 1

    for line in subs.events:
        process_bilingual_event(line, height, is_portrait, zh_factor, en_factor, zh_color, en_color)
    subs.save(ass_path)


def create_preview_frame(video_path, subtitle_path, output_image,
                         ffmpeg_path, ffprobe_path,
                         zh_factor, en_factor, margin_v, zh_color, en_color) -> bool:
    """智能预览：修复了修改边距不移动的问题."""
    try:
        width, height, duration = probe_video_info(video_path, ffprobe_path)
        is_portrait = height > width
        try:
            subs = pysubs2.load(subtitle_path)
        except:
            return False
        if not subs.events: return False

        # 挑出内容最长的一句字幕预览
        target_sub = max(subs.events, key=lambda e: get_text_weight(e.text))
        sub_start_sec = target_sub.start / 1000.0

        # 安全时间定位
        seek_timestamp = sub_start_sec + 0.5
        if duration > 0 and seek_timestamp >= duration:
            seek_timestamp = duration / 2.0

        preview_subs = pysubs2.SSAFile()
        preview_subs.info["WrapStyle"] = "1"

        # --- 核心修复：为预览用的临时文件应用 UI 传进来的 margin_v ---
        style = preview_subs.styles["Default"]
        style.alignment = 2
        style.marginv = margin_v if margin_v is not None else int(height * 0.1)
        style.fontsize = int(height * 0.04)
        style.outline = 2
        style.shadow = 1

        preview_event = target_sub.copy()
        preview_event.start, preview_event.end = 0, 5000
        process_bilingual_event(preview_event, height, is_portrait, zh_factor, en_factor, zh_color, en_color)
        preview_subs.events.append(preview_event)

        video_dir = os.path.dirname(os.path.abspath(video_path))
        temp_ass = os.path.join(video_dir, f"_pre_{os.getpid()}.ass")
        preview_subs.save(temp_ass)

        # 使用相对文件名配合 setWorkingDirectory 避开路径转义问题
        args = ["-y", "-ss", str(seek_timestamp), "-i", video_path,
                "-vf", f"ass='{os.path.basename(temp_ass)}'", "-frames:v", "1", output_image]

        from PyQt5.QtCore import QProcess, QEventLoop
        proc = QProcess()
        proc.setWorkingDirectory(video_dir)
        proc.start(ffmpeg_path, args)
        loop = QEventLoop()
        proc.finished.connect(loop.quit)
        QtCore.QTimer.singleShot(15000, loop.quit)
        loop.exec_()

        if os.path.exists(temp_ass): os.remove(temp_ass)
        return os.path.exists(output_image) and os.path.getsize(output_image) > 0
    except:
        return False


class SubtitleEmbedder(QtCore.QObject):
    progress = QtCore.pyqtSignal(int)
    finished = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)

    def __init__(self, ffmpeg_path: str, ffprobe_path: str, parent=None):
        super().__init__(parent)
        self.ffmpeg_path, self.ffprobe_path = ffmpeg_path, ffprobe_path
        self.proc = QtCore.QProcess(self)
        self.proc.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._on_output)
        self.proc.finished.connect(self._on_finished)
        self._duration_sec = 0

    def embed(self, video_path, srt_path, output_path, zh_factor, en_factor, margin, zh_col, en_col):
        self._output_video = output_path
        self._duration_sec = 0
        video_dir = os.path.dirname(os.path.abspath(video_path))
        self._temp_ass = os.path.join(video_dir, f".tmp_{os.getpid()}.ass")

        try:
            convert_srt_to_ass(video_path, srt_path, self._temp_ass, self.ffmpeg_path, self.ffprobe_path,
                               zh_factor, en_factor, margin, zh_col, en_col)
        except Exception as e:
            self.error.emit(str(e));
            return

        # -nostdin 解决 FFmpeg 挂起卡死问题
        args = ["-y", "-nostdin", "-i", video_path, "-vf", f"ass='{os.path.basename(self._temp_ass)}'",
                "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-c:a", "copy", "-sn", output_path]

        self.proc.setWorkingDirectory(video_dir)
        self.proc.start(self.ffmpeg_path, args)

    def _on_output(self):
        out = self.proc.readAllStandardOutput().data().decode("utf-8", errors="ignore")
        if self._duration_sec == 0:
            m = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", out)
            if m: h, m, s = map(float, m.groups()); self._duration_sec = h * 3600 + m * 60 + s

        # 正确的进度正则
        tm = re.search(r"time=(\d{2}):(\d{2}):(\d{2}\.\d{2})", out)
        if tm and self._duration_sec > 0:
            h, m, s = map(float, tm.groups())
            p = int(((h * 3600 + m * 60 + s) / self._duration_sec) * 100)
            self.progress.emit(min(p, 98))  # 进度条平滑锁定在 98% 等待收尾

    def _on_finished(self, code):
        if hasattr(self, '_temp_ass') and os.path.exists(self._temp_ass):
            try:
                os.remove(self._temp_ass)
            except:
                pass
        if code == 0 and os.path.exists(self._output_video):
            self.progress.emit(100)
            self.finished.emit(self._output_video)
        else:
            self.error.emit(f"嵌入失败 (Code: {code})")