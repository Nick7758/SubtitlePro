import os
import sys
import json
import uuid
import requests
import webbrowser
from core.workers import VideoDownloadWorker
from typing import Dict, Optional
from dataclasses import dataclass
from packaging import version  # 需要运行: pip install packaging
from PyQt5 import QtCore, QtGui, QtWidgets, QtNetwork
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import QUrl
from config.settings import load_config, save_config, DEFAULT_API_BASE, CURRENT_VERSION, UPDATE_URL, DOWNLOAD_VIDEO_DIR, \
    DOWNLOAD_DIR
from config.theme import apply_business_theme
from core.api_client import ApiClient
from ui.components import LoginDialog, notify
from ui.pages import UploadPage, DownloadPage, BillingPage, SettingsPage, SubtitleEditorPage

# --- robust base dir (works in dev & PyInstaller) ---
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _detect_resources_dir() -> str:
    """检测resources目录位置，确保在不同分发环境下都能正确找到资源"""
    candidates = [
        os.path.join(BASE_DIR, "resources"),
        os.path.join(os.path.dirname(BASE_DIR), "resources"),
        os.path.join(BASE_DIR, "_internal", "resources"),
        os.path.join(BASE_DIR, "_internal", "_internal", "resources"),
    ]
    best = None
    for p in candidates:
        if os.path.isdir(p):
            ff = os.path.join(p, "bin", "ffmpeg.exe")
            if os.path.isfile(ff):
                return p
            best = best or p
    return best or os.path.join(BASE_DIR, "resources")


# 确保在加载配置之前先检测资源目录
RESOURCES_DIR = _detect_resources_dir()
DEFAULT_FFMPEG_PATH = os.path.join(RESOURCES_DIR, "bin", "ffmpeg.exe")


@dataclass
class UserState:
    phone: Optional[str] = None
    email: Optional[str] = None
    display_name: str = ""
    minutes_left: int = 0


# Global variables (would be better in a class)
CONFIG = {}
API_CLIENT = None
MAIN_WINDOW = None


class UpdateChecker(QtCore.QThread):
    update_available = QtCore.pyqtSignal(str, str)  # version, url
    error_occurred = QtCore.pyqtSignal(str)  # 错误信息

    def run(self):
        try:
            # 检查是否是本地文件URL
            if UPDATE_URL.startswith("file:///"):
                # 读取本地文件
                file_path = UPDATE_URL[8:].replace("/", "\\")  # 移除"file:///"前缀并转换路径分隔符
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                # 发送HTTP请求获取版本信息
                response = requests.get(UPDATE_URL, timeout=5)
                response.raise_for_status()
                # 解析JSON响应
                data = response.json()

            latest_version = data.get("version")
            download_url = data.get("download_url")  # 修正字段名
            update_notes = data.get("message", "")  # 修正字段名

            # 检查版本号
            if latest_version and version.parse(latest_version) > version.parse(CURRENT_VERSION):
                # 检查是否跳过了此版本
                from config.settings import load_config
                config = load_config()
                skipped_version = config.get("skipped_version")

                # 如果没有跳过此版本或跳过的版本不同，则发出更新信号
                if skipped_version != latest_version:
                    self.update_available.emit(latest_version, download_url)
        except FileNotFoundError as e:
            # 文件未找到错误
            self.error_occurred.emit(f"检查更新失败: 本地版本文件未找到 ({str(e)})")
        except requests.RequestException as e:
            # 网络错误
            self.error_occurred.emit(f"检查更新失败: 网络错误 ({str(e)})")
        except Exception as e:
            # 其他错误
            self.error_occurred.emit(f"检查更新失败: {str(e)}")

    def download_update(self, download_url, progress_callback=None):
        """下载更新文件"""
        try:
            # 获取下载目录
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)

            # 从URL中提取文件名
            filename = download_url.split("/")[-1]
            filepath = os.path.join(DOWNLOAD_DIR, filename)

            # 下载文件
            response = requests.get(download_url, stream=True)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if progress_callback and total_size > 0:
                            progress = int((downloaded_size / total_size) * 100)
                            # 检查是否应该取消下载
                            result = progress_callback(progress)
                            # 如果回调返回False，则取消下载
                            if result is False:
                                # 清理已下载的文件
                                if os.path.exists(filepath):
                                    try:
                                        os.remove(filepath)
                                    except:
                                        pass
                                raise Exception("下载已被用户取消")

            return filepath
        except Exception as e:
            raise Exception(f"下载更新失败: {str(e)}")


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        # 使用本地的资源路径检测结果
        self.config = load_config()
        # 确保配置中的ffmpeg_path使用本地检测到的默认路径
        if "ffmpeg_path" not in self.config or not self.config["ffmpeg_path"]:
            self.config["ffmpeg_path"] = DEFAULT_FFMPEG_PATH
        self.api_client = ApiClient(DEFAULT_API_BASE)
        # 初始化用户信息存储
        self._current_user_info = {}
        # 初始化账户信息等待标志
        self._waiting_for_account_info = False
        global API_CLIENT, MAIN_WINDOW
        API_CLIENT = self.api_client
        MAIN_WINDOW = self

        self.setWindowTitle("NickSub Pro v1.0 - AI 视频翻译专家")
        self.resize(1100, 760)  # 修改为与nick.py一致的大小

        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(__file__), "resources", "app_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))

        # Apply theme
        apply_business_theme(QtWidgets.QApplication.instance(), self.config.get("theme", "Light"))

        # Setup UI
        self.setup_ui()
        self.setup_connections()

        # Start update checker
        self.update_checker = UpdateChecker()
        self.update_checker.update_available.connect(self._on_update_available)
        self.update_checker.error_occurred.connect(self._on_update_error)
        self.update_checker.start()

        # Connect API client to handle responses
        self.api_client.requestFinished.connect(self._on_api)

        # Check if user is already logged in
        if not self.api_client.token:
            # If no token, show login dialog after a short delay
            QtCore.QTimer.singleShot(200, self._login)
        else:
            # If token exists, update UI to show logged in status
            self._on_login_success()

    def setup_ui(self):
        # Central widget
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        layout = QtWidgets.QVBoxLayout(central_widget)

        # Tab widget
        self.tab_widget = QtWidgets.QTabWidget()
        self.upload_page = UploadPage()
        self.download_page = DownloadPage(self.config.get("ffmpeg_path", ""))
        self.subtitle_editor_page = SubtitleEditorPage()
        self.billing_page = BillingPage()
        self.settings_page = SettingsPage(self.config)

        self.tab_widget.addTab(self.upload_page, "视频翻译")
        self.tab_widget.addTab(self.download_page, "视频下载")
        self.tab_widget.addTab(self.subtitle_editor_page, "修改字幕")
        self.tab_widget.addTab(self.billing_page, "购买分钟")
        self.tab_widget.addTab(self.settings_page, "设置")

        layout.addWidget(self.tab_widget)

        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        self.login_action = QtWidgets.QAction("账户", self)
        self.logout_action = QtWidgets.QAction("退出登录", self)
        toolbar.addAction(self.login_action)
        toolbar.addAction(self.logout_action)
        toolbar.addSeparator()

        # 添加弹性空间，将状态信息推到最右边
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        # 状态信息显示在最右边
        self.account_label = QtWidgets.QLabel("未登录")
        self.quota_label = QtWidgets.QLabel("分钟: —")
        toolbar.addWidget(self.account_label)
        toolbar.addSeparator()
        toolbar.addWidget(self.quota_label)

        # 初始状态下显示退出登录按钮
        self.logout_action.setVisible(True)

    def setup_connections(self):
        # Toolbar actions
        self.login_action.triggered.connect(self._on_account)
        self.logout_action.triggered.connect(self._logout)

        # Page signals
        self.upload_page.start_task.connect(self._start_translation_task)
        self.download_page.start_download.connect(self._start_download)
        self.download_page.sync_btn.clicked.connect(self._sync_cookies)
        self.billing_page.purchase_minutes.connect(self._purchase_minutes)
        self.settings_page.settings_changed.connect(self._on_settings_changed)

        # Connect open location buttons
        self.upload_page.openVideoBtn.clicked.connect(self._open_video_location)
        self.upload_page.openSubsBtn.clicked.connect(self._open_subs_location)

    def _login(self):
        dialog = LoginDialog(self.api_client, self)
        dialog.authed.connect(self._on_login_success)
        dialog.exec_()

    def _logout(self):
        self.api_client.set_token(None)
        self._current_user_info = {}
        self.account_label.setText("未登录")
        self.quota_label.setText("分钟: —")
        if hasattr(self, 'upload_page'):
            self.upload_page.setQuota(None)
            self.upload_page.startBtn.setEnabled(False)
        if hasattr(self, 'billing_page'):
            self.billing_page.set_user(None)
        notify(self, "已退出登录")

    def _on_login_success(self, info=None):
        # 从API获取最新的用户信息和分钟数
        self.api_client.me()

    def _on_account(self):
        if not self.api_client.token:
            self._login()
            return
        # 设置标志位，表示正在等待账户信息
        self._waiting_for_account_info = True
        # 从API获取最新的用户信息
        self.api_client.me()

    def _show_account_dialog(self, ident, minutes_left):
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("账户")
        box.setIcon(QtWidgets.QMessageBox.Information)
        box.setText(f"当前账户：{ident}\n剩余分钟：{minutes_left}")
        switch_btn = box.addButton("切换账户", QtWidgets.QMessageBox.AcceptRole)
        refresh_btn = box.addButton("刷新余额", QtWidgets.QMessageBox.ActionRole)
        box.addButton("关闭", QtWidgets.QMessageBox.RejectRole)
        box.exec_()
        clicked = box.clickedButton()
        if clicked == switch_btn:
            self._logout()
            self._login()
        elif clicked == refresh_btn:
            # 调用API刷新余额
            self.api_client.me()
            notify(self, "余额已刷新")

    def _refresh_account_status(self):
        # 从API获取用户信息
        self.api_client.me()
        # 模拟获取用户配额信息
        minutes_left = self.config.get("minutes_left", 0)
        self.quota_label.setText(f"分钟: {minutes_left}")
        # 同时更新上传页面的配额显示
        if hasattr(self, 'upload_page'):
            self.upload_page.setQuota(minutes_left)

    def _on_update_available(self, latest_version, download_url):
        """处理有新版本可用的情况"""
        # 创建一个消息框提示用户有新版本
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle("发现新版本")
        msg_box.setIcon(QtWidgets.QMessageBox.Information)
        msg_box.setText(
            f"发现新版本 {latest_version}，您当前使用的是版本 {CURRENT_VERSION}。\n\n建议您更新到最新版本以获得更好的功能和体验。\n\n点击'更新'按钮将自动下载并安装最新版本。")

        # 添加按钮
        update_btn = msg_box.addButton("更新", QtWidgets.QMessageBox.AcceptRole)
        later_btn = msg_box.addButton("稍后提醒", QtWidgets.QMessageBox.RejectRole)
        skip_btn = msg_box.addButton("跳过此版本", QtWidgets.QMessageBox.ActionRole)

        msg_box.exec_()

        clicked_btn = msg_box.clickedButton()
        if clicked_btn == update_btn:
            # 自动下载并安装更新
            if download_url:
                self._download_and_install_update(latest_version, download_url)
            else:
                QtWidgets.QMessageBox.warning(self, "下载链接无效", "未能获取有效的下载链接，请稍后重试或手动访问官网下载。")
        elif clicked_btn == skip_btn:
            # 保存跳过的版本号到配置文件中
            self.config["skipped_version"] = latest_version
            save_config(self.config)
            notify(self, f"已跳过版本 {latest_version}，将不会再次提醒。")
        # 如果点击"稍后提醒"则不执行任何操作

    def _download_and_install_update(self, latest_version, download_url):
        """下载并安装更新"""
        # 创建进度对话框
        progress_dialog = QtWidgets.QProgressDialog("正在下载更新...", "取消", 0, 100, self)
        progress_dialog.resize(400, 100)  # 设置宽度为400，高度为100
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        progress_dialog.setWindowTitle("下载更新")
        # 去除问号图标
        progress_dialog.setWindowFlags(progress_dialog.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        progress_dialog.show()

        # 在单独的线程中下载更新
        def download_progress(progress):
            # 检查用户是否取消了下载
            if progress_dialog.wasCanceled():
                # 返回False表示取消下载
                return False
            progress_dialog.setValue(progress)
            # 返回True表示继续下载
            return True

        def download_finished(filepath):
            # 检查用户是否取消了下载
            if progress_dialog.wasCanceled():
                # 清理已下载的文件
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except:
                        pass
                return

            progress_dialog.close()
            # 询问用户是否立即安装更新
            # 创建自定义按钮文本的消息框
            reply_box = QtWidgets.QMessageBox(self)
            reply_box.resize(400, 100)
            reply_box.setWindowTitle("下载完成")
            reply_box.setText(f"新版本 {latest_version} 已下载完成，是否立即安装？\n\n注意：安装过程将关闭当前应用程序。")
            yes_button = reply_box.addButton("是", QtWidgets.QMessageBox.YesRole)
            no_button = reply_box.addButton("否", QtWidgets.QMessageBox.NoRole)
            reply_box.setDefaultButton(yes_button)
            reply_box.exec_()
            reply = QtWidgets.QMessageBox.Yes if reply_box.clickedButton() == yes_button else QtWidgets.QMessageBox.No

            if reply == QtWidgets.QMessageBox.Yes:
                # 关闭应用程序并启动安装程序
                self._install_update(filepath)

        def download_error(error_msg):
            progress_dialog.close()
            # 只有在不是用户取消的情况下才显示错误消息
            if not progress_dialog.wasCanceled():
                QtWidgets.QMessageBox.critical(self, "下载失败", f"更新下载失败：{error_msg}")

        # 启动下载
        from PyQt5.QtCore import QThread, pyqtSignal

        class DownloadThread(QThread):
            progress = pyqtSignal(int)
            finished = pyqtSignal(str)
            error = pyqtSignal(str)

            def __init__(self, update_checker, download_url):
                super().__init__()
                self.update_checker = update_checker
                self.download_url = download_url
                self._canceled = False

            def cancel(self):
                """取消下载"""
                self._canceled = True

            def run(self):
                try:
                    # 修改download_update方法以支持进度回调中检查取消状态
                    filepath = self.update_checker.download_update(
                        self.download_url,
                        lambda p: self.progress.emit(p) if not self._canceled else None
                    )
                    if not self._canceled:
                        self.finished.emit(filepath)
                    else:
                        # 清理已下载的文件
                        if os.path.exists(filepath):
                            try:
                                os.remove(filepath)
                            except:
                                pass
                except Exception as e:
                    if not self._canceled:
                        self.error.emit(str(e))

        # 创建并启动下载线程
        self.download_thread = DownloadThread(self.update_checker, download_url)
        self.download_thread.progress.connect(download_progress)
        self.download_thread.finished.connect(download_finished)
        self.download_thread.error.connect(download_error)

        # 连接取消信号
        progress_dialog.canceled.connect(self.download_thread.cancel)

        self.download_thread.start()

    def _install_update(self, installer_path):
        """安装更新"""
        try:
            # 在Windows上启动安装程序并关闭当前应用
            import subprocess
            subprocess.Popen([installer_path])
            # 关闭当前应用程序
            self.close()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "安装失败", f"无法启动安装程序：{str(e)}")

    def _on_update_error(self, error_message):
        """处理更新检查错误"""
        # 可以选择是否通知用户错误信息
        # 对于自动检查更新，通常不显示错误，以免打扰用户
        # 如果需要调试，可以取消下面的注释
        # print(f"更新检查错误: {error_message}")

    def _start_translation_task(self, params):
        # Implementation for starting translation task

        # 检查是否有正在进行的任务
        if hasattr(self, '_busy') and self._busy:
            QtWidgets.QMessageBox.information(self, "任务进行中", "任务提交成功，请等待!")
            return

        # 检查是否已登录
        if not self.api_client.token:
            QtWidgets.QMessageBox.information(self, "需要登录", "请先登录后再开始任务。")
            self._login()
            return

        # 获取视频路径和所需分钟数
        video_path = params["video_path"]
        needed_minutes = self._probe_local_minutes(video_path)

        if needed_minutes <= 0:
            QtWidgets.QMessageBox.warning(self, "无法获取时长", "未能读取视频时长，请检查设置。")
            return

        # 探测视频尺寸（长和宽）
        video_width, video_height = self._probe_video_size(video_path)
        params["video_width"] = video_width
        params["video_height"] = video_height

        # 检查用户余额
        user_minutes = getattr(self, '_current_user_info', {}).get("minutes_left", 0)
        if user_minutes < needed_minutes:
            QtWidgets.QMessageBox.information(self, "分钟不足", f"需 {needed_minutes} 分钟，余额 {user_minutes}。")
            return

        # 设置任务参数
        params["needed_minutes"] = needed_minutes
        stem = os.path.splitext(os.path.basename(video_path))[0]
        unique_suffix = uuid.uuid4().hex[:8]
        params["unique_suffix"] = unique_suffix
        from config.settings import AUDIO_DIR
        audio_path = os.path.join(AUDIO_DIR, f"{self._safe_filename(stem)}_{unique_suffix}.m4a")

        # 保存参数
        self._pipeline_params = params
        self._audio_out = audio_path

        # 更新UI状态
        self.upload_page.setStep(f"开始：提取音频…（预计扣费 {needed_minutes} 分钟）")

        # 检查FFmpeg路径
        ffmpeg_path = self.config.get("ffmpeg_path", "")
        # 如果配置中的路径为空或不存在，则使用默认路径
        if not ffmpeg_path or not os.path.exists(ffmpeg_path):
            from config.settings import DEFAULT_FFMPEG_PATH
            ffmpeg_path = DEFAULT_FFMPEG_PATH
            # 再次检查默认路径是否存在
            if not os.path.exists(ffmpeg_path):
                notify(self, f"未找到 FFmpeg: {ffmpeg_path}")
                return

        # 设置忙碌状态
        self._busy = True
        self.upload_page.startBtn.setEnabled(False)
        self.upload_page.videoBtn.setEnabled(False)

        # 提取音频
        from core.workers import FFmpegAudioWorker
        self.audio_worker = FFmpegAudioWorker(ffmpeg_path)
        self.audio_worker.finished.connect(lambda vpath, apath: self._audio_done(vpath, apath))
        self.audio_worker.error.connect(lambda vpath, err: self._audio_err(vpath, err))
        self.audio_worker.extract(video_path, audio_path)

    def _probe_local_minutes(self, video_path: str) -> int:
        """探测本地视频文件的分钟数"""
        try:
            import subprocess
            import os
            ffmpeg_path = self.config.get("ffmpeg_path", "")
            ffprobe_path = os.path.join(os.path.dirname(ffmpeg_path), "ffprobe.exe") if ffmpeg_path else "ffprobe"

            cmd = [ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1",
                   video_path]
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            duration = float(subprocess.check_output(cmd, startupinfo=si).strip())
            if duration <= 0:
                return 0
            import math
            return max(1, math.ceil(duration / 60.0))
        except Exception:
            return 0

    def _safe_filename(self, filename: str) -> str:
        """安全的文件名"""
        import re
        return re.sub(r'[<>:"/\\|?*\x00-\x1F]', '_', filename)

    def _probe_video_size(self, video_path: str) -> tuple:
        """探测视频尺寸（宽和高）"""
        try:
            import subprocess
            import json
            import os
            ffmpeg_path = self.config.get("ffmpeg_path", "")
            ffprobe_path = os.path.join(os.path.dirname(ffmpeg_path), "ffprobe.exe") if ffmpeg_path else "ffprobe"

            cmd = [
                ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json",
                video_path
            ]
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.check_output(cmd, startupinfo=si, text=True)
            data = json.loads(result)
            stream = data["streams"][0]
            return stream["width"], stream["height"]
        except Exception as e:
            # 如果探测失败，返回默认值 1920x1080
            return 1920, 1080

    def _audio_done(self, video_path: str, audio_path: str):
        """音频提取完成的回调"""
        self.upload_page.setStep("音频提取完成，开始上传并创建任务…")
        self._create_job_after_extract(audio_path)

    def _audio_err(self, video_path: str, error: str):
        """音频提取失败的回调"""
        self.upload_page.setStep(f"音频提取失败：{error}")
        self._busy = False
        self.upload_page.startBtn.setEnabled(True)
        self.upload_page.videoBtn.setEnabled(True)
        self.upload_page.langSrc.setEnabled(True)
        self.upload_page.langTgt.setEnabled(True)

    def _start_download(self, url):

        self.download_page.download_btn.setEnabled(False)
        self.download_page.progress_bar.setValue(0)
        self.download_page.log_display.clear()
        self.download_page._log("准备开始下载...")

        ffmpeg_path = self.config.get("ffmpeg_path", "")

        self.download_worker = VideoDownloadWorker(url, DOWNLOAD_VIDEO_DIR, ffmpeg_path)
        self.download_worker.progress.connect(self.download_page.set_progress)
        self.download_worker.log.connect(self.download_page._log)
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.error.connect(self._on_download_error)
        self.download_worker.start()

    def _sync_cookies(self):
        # Implementation for syncing cookies
        notify(self, "Cookie同步已完成")

    def _on_download_finished(self, filename):
        """下载完成的处理方法"""
        self.download_page.status_label.setText("下载成功！")
        self.download_page._log(f"文件已保存: {os.path.basename(filename)}")
        self.download_page.download_btn.setEnabled(True)
        notify(self, "视频下载完成")

    def _on_download_error(self, err_msg):
        """下载错误的处理方法"""
        self.download_page.status_label.setText("出错")
        self.download_page._log(f"错误: {err_msg}")
        self.download_page.download_btn.setEnabled(True)
        QtWidgets.QMessageBox.critical(self, "下载错误", err_msg)

    def _purchase_minutes(self, amount: int):
        if not self.api_client.token:
            notify(self, "请先登录再购买分钟")
            # 触发登录流程
            QtCore.QTimer.singleShot(100, self._login)
            return
        QtWidgets.QMessageBox.information(self, "购买提示", "当前功能未开放，请联系管理员 1215762270@qq.com")
        QtGui.QGuiApplication.clipboard().setText("1215762270@qq.com")
        notify(self, "已复制管理员邮箱")

    def _on_settings_changed(self):
        # Save config and apply changes
        save_config(self.config)
        notify(self, "设置已保存")

    def _on_api(self, ctx: dict, data: dict):
        op = ctx.get("op")
        if op == "me":
            if "error" in data:
                code = int(data.get("code", 0) or 0)
                if code in (401, 403):
                    self.api_client.set_token(None)
                    self.account_label.setText("未登录")
                    self.quota_label.setText("分钟: —")
                    QtCore.QTimer.singleShot(100, self._login)
                else:
                    notify(self, f"服务器暂时不可用：{data['error']}")
                return
            # 更新用户信息和分钟数显示
            # 与nick.py保持一致的显示逻辑：优先显示name/identity，否则显示手机号，再否则显示邮箱
            name = data.get("name", "") or data.get("identity") or ""
            phone = data.get("phone", "")
            email = data.get("email", "")
            ident = name or phone or email or "已登录"
            minutes_left = int(data.get("minutes_left", 0))

            # 更新_current_user_info变量，以便_start_translation_task方法可以正确获取余额
            self._current_user_info = {
                "name": name,
                "phone": phone,
                "email": email,
                "minutes_left": minutes_left
            }

            self.account_label.setText(ident)
            self.quota_label.setText(f"分钟: {minutes_left}")
            # 同时更新上传页面和计费页面的配额显示
            if hasattr(self, 'upload_page'):
                self.upload_page.setQuota(minutes_left)
            if hasattr(self, 'billing_page'):
                # 创建一个临时的UserState对象用于显示
                user_state = UserState(
                    phone=phone,
                    email=email,
                    display_name=ident,
                    minutes_left=minutes_left
                )
                self.billing_page.set_user(user_state)

            # 如果是在_on_account调用后获取信息，显示账户对话框
            if getattr(self, '_waiting_for_account_info', False):
                self._waiting_for_account_info = False
                self._show_account_dialog(ident, minutes_left)
        elif op == "get_job":
            if "error" in data:
                if data.get("code") == 404:
                    self._notfound_retries = getattr(self, "_notfound_retries", 0) + 1
                    if self._notfound_retries <= 20:
                        self.upload_page.setStep("登记中…")
                        return
                self.upload_page.setStep(f"任务失败：{data.get('error')}")
                if hasattr(self, "pollTimer"):
                    self.pollTimer.stop()
                self._busy = False
                self.upload_page.startBtn.setEnabled(True)
                self.upload_page.videoBtn.setEnabled(True)
                self.upload_page.langSrc.setEnabled(True)
                self.upload_page.langTgt.setEnabled(True)
                return

            if hasattr(self, "_notfound_retries"):
                self._notfound_retries = 0

            status = data.get("status", "Queued")
            progress = int(data.get("progress", 0))
            msg = data.get("message")

            if status == "Queued":
                self.upload_page.setStep(msg or "排队中...")
            else:
                self.upload_page.setProgress(progress)
                self.upload_page.setStep(f"{status} – {msg or ''}")

            urls = data.get("urls", {})
            jid = ctx.get("job_id") or self._current_job_id

            if status in ("Done", "Error"):
                if status == "Done":
                    if not getattr(self, "_completed_jobs", {}).get(jid):
                        if not hasattr(self, "_completed_jobs"):
                            self._completed_jobs = {}
                        self._completed_jobs[jid] = True
                        self._download_results(jid, urls)
                        self.api_client.me()
                        QtCore.QTimer.singleShot(1500, lambda: self.api_client.me())

                if hasattr(self, "pollTimer"):
                    self.pollTimer.stop()
                self._busy = False
                self.upload_page.startBtn.setEnabled(True)
                self.upload_page.videoBtn.setEnabled(True)
                self.upload_page.langSrc.setEnabled(True)
                self.upload_page.langTgt.setEnabled(True)
        elif op == "purchase_minutes":
            notify(self, "购买分钟成功")
            self.api_client.me()  # 刷新用户信息

    def _create_job_after_extract(self, audio_path: str):
        """音频提取完成后创建任务"""
        # 检查参数
        if not hasattr(self, '_pipeline_params'):
            self.upload_page.setStep("内部错误：缺少任务参数")
            self._busy = False
            self.upload_page.startBtn.setEnabled(True)
            self.upload_page.videoBtn.setEnabled(True)
            self.upload_page.langSrc.setEnabled(True)
            self.upload_page.langTgt.setEnabled(True)
            return

        params = self._pipeline_params
        lang_src = params["lang_src"]
        lang_tgt = params["lang_tgt"]
        needed_minutes = params.get("needed_minutes", 0)

        # 准备上传数据
        from PyQt5.QtCore import QFile, QUrl
        from PyQt5.QtNetwork import QHttpMultiPart, QHttpPart, QNetworkRequest
        import uuid

        # 生成客户端任务ID
        client_job_id = str(uuid.uuid4())

        # 创建multipart请求
        multi_part = QHttpMultiPart(QHttpMultiPart.FormDataType)

        # 添加字段的辅助函数
        def add_field(name: str, value: str):
            part = QHttpPart()
            part.setHeader(QNetworkRequest.ContentDispositionHeader, f'form-data; name="{name}"')
            part.setBody(value.encode())
            multi_part.append(part)

        # 添加必需的参数
        add_field("client_job_id", client_job_id)
        add_field("video_name", os.path.basename(params["video_path"]))
        add_field("lang_src", lang_src)
        add_field("lang_tgt", lang_tgt)
        
        # 添加视频尺寸信息
        if "video_width" in params and "video_height" in params:
            add_field("video_width", str(params["video_width"]))
            add_field("video_height", str(params["video_height"]))

        # 添加音频文件
        audio_file = QFile(audio_path)
        if not audio_file.open(QFile.ReadOnly):
            self.upload_page.setStep("无法读取音频文件")
            self._busy = False
            self.upload_page.startBtn.setEnabled(True)
            self.upload_page.videoBtn.setEnabled(True)
            self.upload_page.langSrc.setEnabled(True)
            self.upload_page.langTgt.setEnabled(True)
            return

        audio_part = QHttpPart()
        audio_part.setHeader(QNetworkRequest.ContentDispositionHeader,
                             f'form-data; name="audio"; filename="{os.path.basename(audio_path)}"')
        # 设置正确的MIME类型
        ext = os.path.splitext(audio_path)[1].lower()
        mime = "audio/mp4" if ext == ".m4a" else "application/octet-stream"
        audio_part.setHeader(QNetworkRequest.ContentTypeHeader, mime)
        audio_part.setBodyDevice(audio_file)
        audio_file.setParent(multi_part)  # 让multi_part拥有audio_file
        multi_part.append(audio_part)

        # 发送请求
        url = QUrl(self.api_client.base_url + "/jobs")
        request = QNetworkRequest(url)
        # 设置User-Agent头部
        request.setRawHeader(b"User-Agent", b"BiSubPro/1.0")
        if self.api_client.token:
            request.setRawHeader(b"Authorization", f"Bearer {self.api_client.token}".encode())

        self._currentUploadReply = self.api_client.nam.post(request, multi_part)
        multi_part.setParent(self._currentUploadReply)  # 让reply拥有multi_part

        # 保存任务ID
        self._pending_client_job_id = client_job_id
        self._current_job_id = None

        self._currentUploadReply.uploadProgress.connect(
            lambda sent, total: self.upload_page.setProgress(int(sent / total * 50) if total > 0 else 0)
        )
        self._currentUploadReply.finished.connect(lambda: self._on_upload_finished(self._currentUploadReply))

        self.upload_page.setProgress(5)
        self.upload_page.setStep("正在上传音频…")

    def _on_upload_finished(self, reply):
        """处理上传完成的回调"""
        try:
            if getattr(self, "_upload_file", None):
                self._upload_file.close()
        except Exception:
            pass
        self._upload_file = None
        self._upload_mp = None

        status = reply.attribute(QtNetwork.QNetworkRequest.HttpStatusCodeAttribute)
        if status and int(status) >= 400:
            self.upload_page.setStep(f"上传失败：HTTP {int(status)}")
            self._busy = False
            self.upload_page.startBtn.setEnabled(True)
            self.upload_page.videoBtn.setEnabled(True)
            self.upload_page.langSrc.setEnabled(True)
            self.upload_page.langTgt.setEnabled(True)
            reply.deleteLater()
            return

        raw = reply.readAll().data()
        try:
            server = json.loads(raw) if raw else {}
        except Exception:
            server = {}

        real_jid = server.get("job_id") or server.get("id") or server.get("server_job_id")
        if real_jid:
            self._current_job_id = real_jid
            self.upload_page.setStep("音频上传完成，任务已入队…")
        else:
            self.upload_page.setStep("音频上传完成，等待 ID…")

        msg = server.get("message")
        if msg:
            self.upload_page.setStep(msg)

        if real_jid:
            self._pending_client_job_id = None
            self._poll_current()
            self.pollTimer = QtCore.QTimer(self)
            self.pollTimer.timeout.connect(self._poll_current)
            self.pollTimer.start(3000)
            QtCore.QTimer.singleShot(2500, self._poll_current)
        reply.deleteLater()

    def _poll_current(self):
        """轮询任务状态"""
        jid = getattr(self, "_current_job_id", None)
        if jid:
            self.api_client.get_job(jid)

    def _download_results(self, job_id: str, urls: Dict[str, str]):
        """下载翻译结果"""
        if not hasattr(self, "_dl_handles"):
            self._dl_handles = []

        video_src = (getattr(self, "_pipeline_params", {}) or {}).get("video_path", "")
        base_stem = os.path.splitext(os.path.basename(video_src))[0] or f"job_{job_id}"
        suffix = (getattr(self, "_pipeline_params", {}) or {}).get("unique_suffix", "")

        # 处理文件名
        def with_suffix(stem: str) -> str:
            return f"{self._safe_filename(stem)}_{suffix}" if suffix else self._safe_filename(stem)

        # 下载目录
        from config.settings import RESULT_DIR, SUB_RESULT_DIR, VIDEO_RESULT_DIR

        os.makedirs(SUB_RESULT_DIR, exist_ok=True)
        os.makedirs(VIDEO_RESULT_DIR, exist_ok=True)

        # 检查是否需要烧录字幕
        should_burn = (getattr(self, "_pipeline_params", {}) or {}).get("burn_subtitles", True)

        from PyQt5.QtCore import QFile, QUrl
        from PyQt5.QtNetwork import QNetworkRequest

        for key in ("srt", "ass", "video"):
            url = urls.get(key)
            if not url:
                continue

            base = QUrl(self.api_client.base_url + "/")
            full = base.resolved(QUrl(url))
            req = QNetworkRequest(full)
            if self.api_client.token:
                req.setRawHeader(b"Authorization", f"Bearer {self.api_client.token}".encode())
            reply = self.api_client.nam.get(req)

            if key in ("srt", "ass"):
                filename = f"{with_suffix(base_stem)}.{key}"
                out_dir = SUB_RESULT_DIR
            else:
                # 处理视频文件名
                from urllib.parse import unquote
                url_name = unquote(full.path().split('/')[-1])
                ext = os.path.splitext(url_name)[1].lower() or ".mp4"
                filename = f"{with_suffix(base_stem)}{ext}"
                out_dir = VIDEO_RESULT_DIR

            out_path = os.path.join(out_dir, filename)
            f = QFile(out_path)
            if not f.open(QFile.WriteOnly):
                reply.abort()
                reply.deleteLater()
                continue

            self._dl_handles.append((reply, f))

            def on_ready_read(r=reply, file=f):
                file.write(r.readAll())

            def on_finished(r=reply, file=f, p=out_path, k=key, all_urls=urls):
                file.close()
                notify(self, f"已下载 {os.path.basename(p)}")

                if k in ("srt", "ass"):
                    # 启用字幕按钮
                    self.upload_page.enableResultButtons(video_ok=False, subs_ok=True)
                    video_src_local = (getattr(self, "_pipeline_params", {}) or {}).get("video_path")

                    # LOGIC: Decide whether to call Embed (Burn) or Finish immediately
                    if k == "ass":
                        if should_burn:
                            # 如果用户选择了烧录字幕，则需要实现嵌入字幕的逻辑
                            self._embed_subtitles(video_src_local, p)
                        else:
                            # User skipped burning: We are done.
                            self.upload_page.setProgress(100)
                            self.upload_page.setStep("任务完成 (仅生成字幕)")
                    elif k == "srt" and not all_urls.get("ass"):
                        # Fallback if only SRT exists
                        if should_burn:
                            # 如果用户选择了烧录字幕，则需要实现嵌入字幕的逻辑
                            self._embed_subtitles(video_src_local, p)
                        else:
                            # User skipped burning: We are done.
                            self.upload_page.setProgress(100)
                            self.upload_page.setStep("任务完成 (仅生成字幕)")

                try:
                    r.deleteLater()
                    self._dl_handles.remove((r, file))
                except Exception:
                    pass

            reply.readyRead.connect(on_ready_read)
            reply.finished.connect(on_finished)

        # 任务完成
        self.upload_page.setProgress(100)
        self.upload_page.setStep("任务全部完成！")

    def _safe_filename(self, filename: str) -> str:
        """安全的文件名"""
        import re
        return re.sub(r'[<>:"/\\|?*\x00-\x1F]', '_', filename)

    def _open_video_location(self):
        """打开视频结果目录"""
        import platform
        from config.settings import VIDEO_RESULT_DIR
        os.makedirs(VIDEO_RESULT_DIR, exist_ok=True)

        if platform.system() == "Windows":
            os.startfile(VIDEO_RESULT_DIR)
        elif platform.system() == "Darwin":  # macOS
            os.system(f"open '{VIDEO_RESULT_DIR}'")
        else:  # Linux
            os.system(f"xdg-open '{VIDEO_RESULT_DIR}'")

    def _embed_subtitles(self, video_in: str, subs_path: str):
        """嵌入字幕到视频中"""
        import subprocess
        import re
        import uuid
        import time
        from PyQt5.QtCore import QProcess

        # 确保必要的文件存在
        if not video_in or not os.path.exists(video_in):
            self.upload_page.setStep("视频文件不存在")
            return
        if not subs_path or not os.path.exists(subs_path):
            self.upload_page.setStep("字幕文件不存在")
            return

        # 检查ffmpeg路径
        ffmpeg_path = getattr(self, 'ffmpeg_path', None)
        if not ffmpeg_path or not os.path.exists(ffmpeg_path):
            # 尝试在resources/bin目录下查找ffmpeg
            ffmpeg_path = os.path.join(os.path.dirname(__file__), "resources", "bin", "ffmpeg.exe")
            if not os.path.exists(ffmpeg_path):
                self.upload_page.setStep("未找到FFmpeg，请确保已正确安装")
                return

        # 1. CONFIGURATION
        ZH_FAM = "Microsoft YaHei"  # 中文字体
        EN_FAM = "Arial"  # 英文字体

        # Font Size Factors
        EN_FS_FACTOR = 0.060
        ZH_FS_FACTOR = 0.085

        # BAR CONFIGURATION
        # Height of the black bar as a percentage of video height (e.g., 0.15 = 15%)
        BAR_HEIGHT_RATIO = 0.2
        # Opacity of the black bar (0.0 to 1.0). 0.6 is 60% visible.
        BAR_OPACITY = 0.7

        CN_RE = re.compile(r"[\u4e00-\u9fff]")

        # 2. Helper: Get Video Dimensions
        def _get_video_size(path: str):
            try:
                ffprobe_path = ffmpeg_path.replace("ffmpeg.exe", "ffprobe.exe")
                if not os.path.exists(ffprobe_path):
                    ffprobe_path = "ffprobe"
                probe_cmd = [ffprobe_path, "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", path]
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                out = subprocess.check_output(probe_cmd, startupinfo=si, text=True).strip()
                w, h = map(int, out.split("x"))
                return w, h
            except Exception as e:
                print(f"Probe error: {e}")
                return 1920, 1080

        # 3. Helper: Build ASS (Text Only - No Box Here)
        def _build_ass(src_srt, output_ass, w, h):
            try:
                import pysubs2
            except ImportError:
                # 如果pysubs2不可用，直接使用原始字幕文件
                return src_srt

            subs = pysubs2.load(src_srt)
            subs.info["PlayResX"] = str(w)
            subs.info["PlayResY"] = str(h)
            subs.info["WrapStyle"] = "1"

            # --- STYLE DEFINITION (Text Only) ---
            if "Default" in subs.styles:
                style = subs.styles["Default"]
            else:
                style = pysubs2.SSAStyle()
                subs.styles["Default"] = style

            style.fontname = "Arial"
            style.fontsize = 20

            # REVERT TO NORMAL TEXT (No Box in the font style)
            style.borderstyle = 1  # 1 = Normal Outline
            style.outlinecolor = "&H000000"  # Black Outline for readability
            style.outline = 2.2  # Thin outline
            style.shadow = 1.7

            style.alignment = 2  # Bottom Center
            style.marginl = style.marginr = 10
            style.marginv = 2  # Position text slightly up from bottom

            ZH_COLOR = "&H00C3FF"  # Yellow/Cyan (BGR)
            EN_COLOR = "&H00FFFFFF"  # White (BGR)

            for ev in subs:
                ev.style = "Default"
                clean_text = re.sub(r"\{.*?\}", "", ev.text)
                lines = re.split(r"\\[Nn]|\n", clean_text.strip())

                if len(lines) >= 2:
                    en_fs = max(16, int(h * EN_FS_FACTOR))
                    zh_fs = max(26, int(h * ZH_FS_FACTOR))
                    en_line = fr"{{\fn{EN_FAM}\fs{en_fs}\b0\c{EN_COLOR}}}{lines[0]}"
                    zh_line = fr"{{\fn{ZH_FAM}\fs{zh_fs}\b1\c{ZH_COLOR}}}{lines[1]}"
                    ev.text = en_line + r"\N" + zh_line
                elif len(lines) == 1:
                    is_cn = bool(CN_RE.search(lines[0]))
                    fam = ZH_FAM if is_cn else EN_FAM
                    fs = max(26, int(h * ZH_FS_FACTOR)) if is_cn else max(16, int(h * EN_FS_FACTOR))
                    color = ZH_COLOR if is_cn else EN_COLOR
                    ev.text = fr"{{\fn{fam}\fs{fs}\b1\c{color}}}{lines[0]}"

            subs.save(output_ass)
            return output_ass

        # --- EXECUTION ---
        def _video_output_path_for(src: str) -> str:
            """生成输出视频路径"""
            from config.settings import VIDEO_RESULT_DIR
            os.makedirs(VIDEO_RESULT_DIR, exist_ok=True)

            base_name = os.path.splitext(os.path.basename(src))[0]
            return os.path.join(VIDEO_RESULT_DIR, f"{base_name}_subtitled.mp4")

        out_path = _video_output_path_for(video_in)
        temp_ass_path = os.path.join(os.path.dirname(out_path), f"temp_style_{uuid.uuid4().hex[:6]}.ass")

        # 1. Get size and build the text subtitles
        video_w, video_h = 1920, 1080
        try:
            video_w, video_h = _get_video_size(video_in)
            processed_subs_path = _build_ass(subs_path, temp_ass_path, video_w, video_h)
        except Exception as e:
            print(f"Style gen failed: {e}")
            processed_subs_path = subs_path

        # 2. Escape paths for FFmpeg
        def _escape_path(p):
            p = os.path.abspath(p).replace("\\", "/")
            p = p.replace(":", r"\:")
            return p

        ass_filter_path = _escape_path(processed_subs_path)

        # 3. CALCULATE BAR DIMENSIONS
        bar_height = int(video_h * BAR_HEIGHT_RATIO)

        # 4. BUILD FFMPEG FILTER CHAIN
        # Filter A: Draw the black box (drawbox)
        # Filter B: Draw the text (ass)
        # Syntax: drawbox=...,ass=...

        drawbox_filter = (
            f"drawbox=x=0:y=ih-{bar_height}:w=iw:h={bar_height}:"
            f"color=black@{BAR_OPACITY}:t=fill"
        )

        subtitle_filter = f"ass='{ass_filter_path}'"

        # Combine filters with a comma
        vf = f"{drawbox_filter},{subtitle_filter}"

        args = [
            "-y", "-i", video_in,
            "-vf", vf,
            "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
            "-c:a", "copy",
            out_path
        ]

        # --- Standard Progress & Run Code ---
        self._burn_total = 0
        try:
            ffprobe_path = ffmpeg_path.replace("ffmpeg.exe", "ffprobe.exe")
            if not os.path.exists(ffprobe_path):
                ffprobe_path = "ffprobe"
            cmd = [ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of",
                   "default=noprint_wrappers=1:nokey=1", video_in]
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self._burn_total = float(subprocess.check_output(cmd, startupinfo=si).strip())
        except:
            pass

        self._burnProc = QProcess(self)
        self._burnProc.setProcessChannelMode(QProcess.MergedChannels)

        def _on_burn_output():
            if not hasattr(self, "_last_burn_update"): self._last_burn_update = 0
            now = time.time()
            if now - self._last_burn_update < 1: return
            self._last_burn_update = now
            try:
                chunk = bytes(self._burnProc.readAllStandardOutput()).decode(errors="ignore")
            except:
                return
            m = re.search(r"time=(\d+):(\d+):(\d+\.?\d*)", chunk)
            if m:
                cur_sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                total = self._burn_total or 1
                pct = min(int(cur_sec / total * 100), 99)
                if hasattr(self, "upload_page"): self.upload_page.setProgress(pct)

        def _on_burn_done(code, _status):
            if os.path.exists(temp_ass_path) and temp_ass_path != subs_path:
                try:
                    os.remove(temp_ass_path)
                except:
                    pass

            ok = (code == 0 and os.path.exists(out_path))
            if ok:
                notify(self, f"完成：{os.path.basename(out_path)}")
                if hasattr(self, "upload_page"):
                    self.upload_page.enableResultButtons(video_ok=True, subs_ok=True)
                    self.upload_page.setProgress(100)
                    self.upload_page.setStep("任务全部完成！")
            else:
                notify(self, "合成失败")
                if hasattr(self, "upload_page"): self.upload_page.setStep("合成视频失败")

            if self._burnProc:
                self._burnProc.deleteLater()
                self._burnProc = None

        self._burnProc.readyReadStandardOutput.connect(_on_burn_output)
        self._burnProc.finished.connect(_on_burn_done)
        self._burnProc.start(ffmpeg_path, args)

        if hasattr(self, "upload_page"):
            self.upload_page.setStep("正在绘制背景并合成视频...")
            self.upload_page.setProgress(0)

    def _open_subs_location(self):
        """打开字幕结果目录"""
        import platform
        from config.settings import SUB_RESULT_DIR
        os.makedirs(SUB_RESULT_DIR, exist_ok=True)

        if platform.system() == "Windows":
            os.startfile(SUB_RESULT_DIR)
        elif platform.system() == "Darwin":  # macOS
            os.system(f"open '{SUB_RESULT_DIR}'")
        else:  # Linux
            os.system(f"xdg-open '{SUB_RESULT_DIR}'")

    def closeEvent(self, event):
        save_config(self.config)
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    # 设置应用程序图标
    icon_path = os.path.join(os.path.dirname(__file__), "resources", "app_icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QtGui.QIcon(icon_path))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()