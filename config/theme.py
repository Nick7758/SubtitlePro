from PyQt5 import QtCore, QtGui, QtWidgets

BUSINESS_QSS = """
/* ===== Mint Business Theme (清新薄荷风) ===== */

/* 基础 */
QMainWindow { background-color: #f6f9f8; }
QWidget {
  background-color: #f6f9f8;
  color: #1f2e2e;
  font-family: "Segoe UI", "Microsoft YaHei";
  font-size: 14px;
}
QToolTip {
  background: #ffffff;
  color: #1f2e2e;
  border: 1px solid #d7e6e3;
  padding: 6px 8px;
  border-radius: 8px;
}

/* 工具栏 */
QToolBar {
  background: #ffffff;
  border-bottom: 1px solid #e3eeeb;
  padding: 4px;
  spacing: 8px;
}
QToolBar QToolButton {
  background: transparent;
  color: #1f2e2e;
  padding: 6px 10px;
  border-radius: 8px;
}
QToolBar QToolButton:hover { background: #eef6f4; }

/* 选项卡 */
QTabWidget::pane {
  border: 1px solid #e0edeb;
  border-radius: 10px;
  top: -1px;
  background: #ffffff;
}
QTabBar::tab {
  background: #eef6f4;
  color: #22403f;
  border: 1px solid #d7e6e3;
  border-bottom: none;
  padding: 8px 16px;
  margin-right: 6px;
  border-top-left-radius: 10px;
  border-top-right-radius: 10px;
}
QTabBar::tab:selected {
  background: #ffffff;
  color: #1f2e2e;
  font-weight: 600;
}

/* 输入类控件 */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {
  background: #ffffff;
  color: #1f2e2e;
  border: 1px solid #cfdedb;
  border-radius: 8px;
  padding: 8px 10px;
  selection-background-color: #b2f1e4;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {
  border: 2px solid #00b894;
}
QLineEdit::placeholder, QTextEdit::placeholder, QPlainTextEdit::placeholder {
  color: #7a8a88;
}

/* 按钮 */
QPushButton {
  background-color: #00b894;
  color: #ffffff;
  border: none;
  border-radius: 8px;
  padding: 9px 15px;
  font-weight: 600;
  min-height: 36px;
}
QPushButton:hover { background-color: #00cea7; }
QPushButton:pressed { background-color: #00a383; }
QPushButton:disabled {
  background-color: #e1eae8;
  color: #9cb3ae;
}

/* 次级扁平按钮（给打开目录等次要动作用）*/
QPushButton#flatBtn {
  background: #ffffff;
  color: #2b4a47;
  border: 1px solid #cfdedb;
  border-radius: 8px;
}
QPushButton#flatBtn:hover { background: #f0fbf8; }

/* 危险按钮 (删除) */
QPushButton#dangerBtn {
  background: #ffffff;
  color: #d63031;
  border: 1px solid #fab1a0;
  border-radius: 8px;
}
QPushButton#dangerBtn:hover { background: #ffeaa7; }


/* 分组/表单 */
QGroupBox {
  border: 1px solid #e0edeb;
  border-radius: 10px;
  margin-top: 10px;
  background: #ffffff;
}
QGroupBox::title {
  subcontrol-origin: margin;
  left: 12px;
  padding: 0 6px;
  color: #3a6a64;
  background: transparent;
}

/* 进度条 */
QProgressBar {
  border: 1px solid #d7e6e3;
  border-radius: 8px;
  background: #eef6f4;
  text-align: center;
  height: 16px;
  color: #1f2e2e;
}
QProgressBar::chunk {
  border-radius: 8px;
  background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #00b894, stop:1 #33e1c9);
}

/* 滚动条 */
QScrollBar:vertical { background: #eef6f4; width: 12px; }
QScrollBar::handle:vertical { background: #cfe5e1; min-height: 36px; border-radius: 6px; }
QScrollBar::handle:vertical:hover { background: #bfe0da; }

/* 标签（信息/弱化） */
QLabel#quotaLabel { font-size: 13px; color: #4f706b; }
QLabel#statusStrong { color: #15332f; font-weight: 600; }
QLabel[role="muted"] { color: #7a8a88; }

/* 消息框 */
QMessageBox { background: #ffffff; color: #1f2e2e; }
QMessageBox QLabel { color: #1f2e2e; }
QMessageBox QPushButton {
  min-width: 92px;
  padding: 8px 12px;
  background: #00b894;
  color: #ffffff;
  border-radius: 6px;
}

/* 文本区域 */
QTextEdit, QPlainTextEdit { background: #ffffff; color: #1f2e2e; }
QLabel { background: transparent; }
"""

def apply_business_theme(app: QtWidgets.QApplication, mode: str = "Dark"):
    app.setStyle("Fusion")
    pal = QtGui.QPalette()
    if mode == "Light":
        base, window, text = QtGui.QColor("#f5f7fb"), QtGui.QColor("#ffffff"), QtGui.QColor("#101828")
        pal.setColor(QtGui.QPalette.Window, window)
        pal.setColor(QtGui.QPalette.WindowText, text)
        pal.setColor(QtGui.QPalette.Base, base)
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#f0f3f9"))
        pal.setColor(QtGui.QPalette.ToolTipBase, window)
        pal.setColor(QtGui.QPalette.ToolTipText, text)
        pal.setColor(QtGui.QPalette.Text, text)
        pal.setColor(QtGui.QPalette.Button, window)
        pal.setColor(QtGui.QPalette.ButtonText, text)
        pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#1d64f2"))
        pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#ffffff"))
        app.setPalette(pal)
        app.setStyleSheet(
            BUSINESS_QSS.replace("#0f1115", "#ffffff").replace("#0b0d11", "#ffffff").replace("#0b0f16", "#f5f7fb"))
    else:
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#0f1115"))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#e6e9ef"))
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor("#0b0f16"))
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#111723"))
        pal.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor("#1a1f29"))
        pal.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor("#e6e9ef"))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor("#e6e9ef"))
        pal.setColor(QtGui.QPalette.Button, QtGui.QColor("#0b0d11"))
        pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#e6e9ef"))
        pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#1d64f2"))
        pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#ffffff"))
        app.setPalette(pal)
        app.setStyleSheet(BUSINESS_QSS)
    app.setFont(QtGui.QFont("Segoe UI", 10))