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
        
        # 创建UI组件
        self.modePhone = QtWidgets.QRadioButton("手机号登录")
        self.modeEmail = QtWidgets.QRadioButton("邮箱登录")
        self.modePhone.setChecked(True)
        self.phoneEdit = QtWidgets.QLineEdit()
        self.phoneEdit.setPlaceholderText("请输入手机号")
        self.emailEdit = QtWidgets.QLineEdit()
        self.emailEdit.setPlaceholderText("请输入邮箱地址")
        self.emailEdit.setVisible(False)
        self.otpEdit = QtWidgets.QLineEdit()
        self.otpEdit.setPlaceholderText("验证码")
        self.otpEdit.setMaxLength(6)
        self.sendBtn = QtWidgets.QPushButton("发送验证码")
        self.verifyBtn = QtWidgets.QPushButton("登录")
        self.verifyBtn.setEnabled(False)
        self.statusLab = QtWidgets.QLabel("")
        self.statusLab.setStyleSheet("color:#888")

        # 布局设置
        modeLay = QtWidgets.QHBoxLayout()
        modeLay.addWidget(self.modePhone)
        modeLay.addWidget(self.modeEmail)
        modeLay.addStretch(1)
        
        form = QtWidgets.QFormLayout()
        form.addRow("登录方式", self._wrap(modeLay))
        form.addRow("手机号/邮箱", self._wrap_two(self.phoneEdit, self.emailEdit))
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
        self.modePhone.toggled.connect(self._toggle_mode)
        
        # 冷却计时器
        self._cooldown = 0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

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

    def _toggle_mode(self, checked: bool):
        is_phone = self.modePhone.isChecked()
        self.phoneEdit.setVisible(is_phone)
        self.emailEdit.setVisible(not is_phone)
        self.stack.setCurrentIndex(0 if is_phone else 1)
        self.verifyBtn.setEnabled(False)
        self.statusLab.setText("")

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
        if not phone and not email:
            self.statusLab.setText("请输入手机号或邮箱")
            return
        self.api.login_send_otp(phone=phone, email=email)

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