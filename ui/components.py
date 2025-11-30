from PyQt5 import QtCore, QtGui, QtWidgets


class Toast(QtWidgets.QWidget):
    """A semi-transparent popup notification widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        self.setStyleSheet("""
            background-color: rgba(50, 50, 50, 180);
            color: white;
            border-radius: 8px;
            padding: 15px;
            font-size: 14px;
        """)
        layout = QtWidgets.QVBoxLayout(self)
        self.label = QtWidgets.QLabel()
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.label)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.close)
        self.resize(300, 60)

    def show_message(self, message: str, duration: int = 2000):
        self.label.setText(message)
        self.adjustSize()
        if self.parent():
            center = self.parent().geometry().center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)
        self.show()
        self.timer.start(duration)


def notify(parent, message: str, duration: int = 2000):
    """Show a toast notification."""
    toast = Toast(parent)
    toast.show_message(message, duration)


class LoginDialog(QtWidgets.QDialog):
    """Login dialog with phone/email switching and OTP verification."""
    # 定义信号
    authed = QtCore.pyqtSignal(dict)

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("NickSub Pro v1.0 – 登录/注册")
        self.setModal(True)
        self.setFixedSize(460, 320)

        # 设置输入法策略
        self.setAttribute(QtCore.Qt.WA_InputMethodEnabled, True)

        # 创建UI组件
        self.modePhone = QtWidgets.QRadioButton("手机号登录")
        self.modeEmail = QtWidgets.QRadioButton("邮箱登录")
        # 暂时不设置默认选中，避免在初始化过程中触发_toggle_mode
        self.phoneEdit = QtWidgets.QLineEdit()
        self.phoneEdit.setPlaceholderText("请输入手机号")
        # 设置输入法策略
        self.phoneEdit.setAttribute(QtCore.Qt.WA_InputMethodEnabled, True)
        self.phoneEdit.setInputMethodHints(QtCore.Qt.ImhNone)
        # 确保启用并可编辑
        self.phoneEdit.setEnabled(True)
        self.phoneEdit.setReadOnly(False)

        self.emailEdit = QtWidgets.QLineEdit()
        self.emailEdit.setPlaceholderText("请输入邮箱地址")
        # 确保邮箱输入框启用并可编辑
        self.emailEdit.setEnabled(True)
        self.emailEdit.setReadOnly(False)
        # 设置输入法策略
        self.emailEdit.setAttribute(QtCore.Qt.WA_InputMethodEnabled, True)
        self.emailEdit.setInputMethodHints(QtCore.Qt.ImhEmailCharactersOnly)

        # 初始化堆叠布局索引
        self.stack = None

        self.otpEdit = QtWidgets.QLineEdit()
        self.otpEdit.setPlaceholderText("验证码")
        self.otpEdit.setMaxLength(6)
        self.sendBtn = QtWidgets.QPushButton("发送验证码")
        self.sendBtn.setEnabled(False)  # 默认禁用
        self.verifyBtn = QtWidgets.QPushButton("登录")
        self.verifyBtn.setEnabled(False)
        self.statusLab = QtWidgets.QLabel("")
        self.statusLab.setStyleSheet("color:#888")

        # 布局设置
        modeLay = QtWidgets.QHBoxLayout()
        modeLay.addWidget(self.modeEmail)
        modeLay.addWidget(self.modePhone)
        modeLay.addStretch(1)

        form = QtWidgets.QFormLayout()
        form.addRow("登录方式", self._wrap(modeLay))
        form.addRow("邮箱/手机号", self._wrap_two(self.phoneEdit, self.emailEdit))
        form.addRow("验证码", self.otpEdit)

        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(self.sendBtn)
        btns.addWidget(self.verifyBtn)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(form)
        lay.addLayout(btns)
        lay.addWidget(self.statusLab)
        lay.addStretch(1)

        # 连接信号和槽
        self.sendBtn.clicked.connect(self._send)
        self.verifyBtn.clicked.connect(self._verify)
        self.api.requestFinished.connect(self._on_api)
        self.modePhone.toggled.connect(lambda checked: self._toggle_mode(checked, True))
        self.modeEmail.toggled.connect(lambda checked: self._toggle_mode(checked, False))
        # 连接初始输入框事件
        self.phoneEdit.textChanged.connect(self._on_input_changed)
        self.emailEdit.textChanged.connect(self._on_input_changed)

        # 冷却计时器
        self._cooldown = 0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        # 确保初始状态正确（在所有组件初始化完成后再设置默认选中状态）
        self.modeEmail.setChecked(True)

    def _wrap(self, widget_or_layout):
        w = QtWidgets.QWidget()
        if isinstance(widget_or_layout, QtWidgets.QLayout):
            w.setLayout(widget_or_layout)
        else:
            lay = QtWidgets.QHBoxLayout(w)
            lay.addWidget(widget_or_layout)
        return w

    def _wrap_two(self, w1, w2):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QStackedLayout(w)
        lay.addWidget(w1)
        lay.addWidget(w2)
        self.stack = lay
        return w

    def _toggle_mode(self, checked: bool, is_phone: bool = None):
        # 只有在checked为True时才执行切换逻辑（避免重复执行）
        if not checked:
            return

        # 如果没有传入is_phone参数，则根据sender确定当前切换的模式
        if is_phone is None:
            sender = self.sender()
            is_phone = (sender == self.modePhone) if sender else self.modePhone.isChecked()

        # 确保stack已初始化后再设置索引
        if self.stack is not None:
            self.stack.setCurrentIndex(0 if is_phone else 1)
        else:
            # 如果stack还未初始化，直接设置输入框可见性
            self.phoneEdit.setVisible(is_phone)
            self.emailEdit.setVisible(not is_phone)

        self.verifyBtn.setEnabled(False)
        self.statusLab.setText("")

        # 确保当前可见的输入框能正常接收焦点并更新占位符文本
        if is_phone:
            # 使用singleShot延迟设置焦点，确保界面更新完成
            QtCore.QTimer.singleShot(0, lambda: self.phoneEdit.setFocus())
            # 确保手机号输入框启用并可编辑
            self.phoneEdit.setEnabled(True)
            self.phoneEdit.setReadOnly(False)
            # 更新占位符文本
            self.phoneEdit.setPlaceholderText("请输入手机号")
        else:
            # 使用singleShot延迟设置焦点，确保界面更新完成
            QtCore.QTimer.singleShot(0, lambda: self.emailEdit.setFocus())
            # 确保邮箱输入框启用并可编辑
            self.emailEdit.setEnabled(True)
            self.emailEdit.setReadOnly(False)
            # 更新占位符文本
            self.emailEdit.setPlaceholderText("请输入邮箱地址")
            # 强制刷新邮箱输入框的状态
            self.emailEdit.repaint()

    def _on_input_changed(self, text):
        # 当输入框有内容时启用发送验证码按钮
        has_content = bool(text.strip())
        self.sendBtn.setEnabled(has_content)

    def _tick(self):
        self._cooldown -= 1
        if self._cooldown <= 0:
            self._timer.stop()
            self.sendBtn.setEnabled(True)
            self.sendBtn.setText("发送验证码")
        else:
            self.sendBtn.setText(f"重发({self._cooldown}s)")

    def _start_cooldown(self, sec=60):
        self._cooldown = sec
        self.sendBtn.setEnabled(False)
        self._timer.start()

    def _send(self):
        is_phone = self.modePhone.isChecked()
        phone = self.phoneEdit.text().strip() if is_phone else None
        email = self.emailEdit.text().strip() if not is_phone else None

        # 验证输入
        if is_phone:
            if not phone:
                self.statusLab.setText("请输入手机号")
                return
            # 手机号格式验证
            if not self._is_valid_phone(phone):
                self.statusLab.setText("手机号格式不正确")
                return
        else:
            if not email:
                self.statusLab.setText("请输入邮箱地址")
                return
            # 邮箱格式验证
            if not self._is_valid_email(email):
                self.statusLab.setText("邮箱格式不正确")
                return

        self.api.login_send_otp(phone=phone, email=email)

    def _is_valid_phone(self, phone):
        """验证手机号格式是否正确"""
        import re
        # 中国手机号格式验证（11位数字，以1开头，第二位为3-9）
        pattern = r'^1[3-9]\d{9}$'
        return re.match(pattern, phone) is not None

    def _is_valid_email(self, email):
        """验证邮箱格式是否正确"""
        import re
        # 更严格的邮箱格式验证
        # 要求域名后缀至少有2个字符，且只包含字母
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            return False

        # 获取域名后缀
        domain_suffix = email.split('.')[-1]
        # 域名后缀只能包含字母
        if not domain_suffix.isalpha():
            return False

        # 域名后缀长度应该在2-10个字符之间（常见域名后缀）
        if len(domain_suffix) < 2 or len(domain_suffix) > 10:
            return False

        return True

    def _verify(self):
        code = self.otpEdit.text().strip()
        if len(code) != 6 or not code.isdigit():
            self.statusLab.setText("验证码应为6位数字")
            return
        is_phone = self.modePhone.isChecked()
        phone = self.phoneEdit.text().strip() if is_phone else None
        email = self.emailEdit.text().strip() if not is_phone else None
        self.api.login_verify(otp=code, phone=phone, email=email)

    def _on_api(self, ctx: dict, data: dict):
        op = ctx.get("op")
        if op == "login_send_otp":
            if "error" in data:
                self.statusLab.setText(f"发送失败：{data['error']}")
            else:
                self.statusLab.setText("验证码已发送")
                self.verifyBtn.setEnabled(True)
                self._start_cooldown(60)
        elif op == "login_verify":
            if "error" in data:
                self.statusLab.setText(f"登录失败：{data['error']}")
                return
            token = data.get("token")
            if token:
                self.api.set_token(token)
                self.statusLab.setText("登录成功！")
                info = {}
                if self.modePhone.isChecked():
                    info["phone"] = self.phoneEdit.text().strip()
                else:
                    info["email"] = self.emailEdit.text().strip()
                self.authed.emit(info)
                # 为了兼容旧代码，我们需要在这里保存用户信息到配置中
                if hasattr(self.parent(), 'config'):
                    config = self.parent().config
                    if self.modePhone.isChecked():
                        config["phone"] = self.phoneEdit.text().strip()
                    else:
                        config["email"] = self.emailEdit.text().strip()
                self.accept()

    def get_credentials(self):
        """Get credentials for compatibility with old code"""
        is_phone = self.modePhone.isChecked()
        mode = "phone" if is_phone else "email"
        identifier = self.phoneEdit.text().strip() if is_phone else self.emailEdit.text().strip()
        otp = self.otpEdit.text().strip()
        return mode, identifier, otp