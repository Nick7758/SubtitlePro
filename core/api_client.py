import json
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass
from PyQt5 import QtCore, QtNetwork
from config.settings import TOKEN_PATH

@dataclass
class UserState:
    phone: Optional[str] = None
    email: Optional[str] = None
    display_name: str = ""
    minutes_left: int = 0

SECRET = b"\x19\xA3\x5D\xC2\x00\xF1\x9B\x73\x2D\x8E\x51\x44\x20\xAA\xEF\x09"

def store_token(token: str):
    b = bytearray(token.encode("utf-8"))
    for i in range(len(b)): b[i] ^= SECRET[i % len(SECRET)]
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, "wb") as f: f.write(b)

def load_token() -> Optional[str]:
    try:
        with open(TOKEN_PATH, "rb") as f:
            b = bytearray(f.read())
        for i in range(len(b)): b[i] ^= SECRET[i % len(SECRET)]
        return bytes(b).decode("utf-8")
    except Exception:
        return None

# --- API Client -------------------------------------------------------

class ApiClient(QtCore.QObject):
    requestFinished = QtCore.pyqtSignal(dict, dict)

    def __init__(self, base_url: str, parent=None):
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.nam = QtNetwork.QNetworkAccessManager(self)
        self.token = load_token()

    def set_token(self, token: Optional[str]):
        self.token = token or None
        if token:
            store_token(token)
        else:
            try:
                os.remove(TOKEN_PATH)
            except Exception:
                pass

    def _mkreq(self, path: str) -> QtNetwork.QNetworkRequest:
        url = QtCore.QUrl(self.base_url + path)
        req = QtNetwork.QNetworkRequest(url)
        req.setRawHeader(b"User-Agent", f"BiSubPro/1.0".encode())
        if self.token: req.setRawHeader(b"Authorization", f"Bearer {self.token}".encode())
        return req

    def _do(self, method: str, path: str, payload: Optional[dict], ctx: dict):
        req = self._mkreq(path)
        if method in ("POST", "PUT"): req.setHeader(QtNetwork.QNetworkRequest.ContentTypeHeader, "application/json")
        body = QtCore.QByteArray(json.dumps(payload).encode()) if payload is not None else QtCore.QByteArray()
        if method == "GET":
            op = self.nam.get(req)
        elif method == "POST":
            op = self.nam.post(req, body)
        elif method == "PUT":
            op = self.nam.put(req, body)
        else:
            op = self.nam.get(req)
        op.finished.connect(lambda op=op, ctx=ctx: self._handle_reply(op, ctx))

    def _handle_reply(self, reply: QtNetwork.QNetworkReply, ctx: dict):
        try:
            status = reply.attribute(QtNetwork.QNetworkRequest.HttpStatusCodeAttribute)
            if status and int(status) >= 400:
                data = reply.readAll().data()
                try:
                    server = json.loads(data) if data else {}
                except Exception:
                    server = {}
                if "detail" in server:
                    self.requestFinished.emit(ctx, {"error": server["detail"], "code": int(status)})
                else:
                    self.requestFinished.emit(ctx, {"error": reply.errorString(), "code": int(status)})
                return
            data = reply.readAll().data()
            server = json.loads(data) if data else {}
            self.requestFinished.emit(ctx, server)
        finally:
            reply.deleteLater()

    def login_send_otp(self, *, phone: Optional[str] = None, email: Optional[str] = None):
        ctx = {"op": "login_send_otp"}
        payload = {}
        if phone: payload["phone"] = phone
        if email: payload["email"] = email
        self._do("POST", "/auth/send_otp", payload, ctx)

    def login_verify(self, *, otp: str, phone: Optional[str] = None, email: Optional[str] = None):
        ctx = {"op": "login_verify"}
        payload = {"otp": otp}
        if phone: payload["phone"] = phone
        if email: payload["email"] = email
        self._do("POST", "/auth/verify", payload, ctx)

    def me(self):
        ctx = {"op": "me"}
        self._do("GET", "/me", None, ctx)

    def get_job(self, job_id: str):
        ctx = {"op": "get_job", "job_id": job_id}
        self._do("GET", f"/jobs/{job_id}", None, ctx)

    def purchase_minutes(self, amount: int):
        ctx = {"op": "purchase_minutes"}
        self._do("POST", "/billing/minutes", {"amount": amount}, ctx)