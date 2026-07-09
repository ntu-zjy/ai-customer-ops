import base64
import hashlib
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi.testclient import TestClient


def test_wecom_kf_callback_verification(app_env, monkeypatch) -> None:
    from app.database import reset_for_tests
    from app.main import create_app

    token = "kf-token"
    receive_id = "ww123456"
    aes_key = b"0" * 32
    encoding_aes_key = base64.b64encode(aes_key).decode("ascii").rstrip("=")
    timestamp = "1720000000"
    nonce = "nonce"
    plain = "hello-wecom"
    encrypted = encrypt_wecom_payload(aes_key, plain, receive_id)
    signature = sign(token, timestamp, nonce, encrypted)

    monkeypatch.setenv("WECOM_KF_TOKEN", token)
    monkeypatch.setenv("WECOM_KF_ENCODING_AES_KEY", encoding_aes_key)
    monkeypatch.setenv("WECOM_CORP_ID", receive_id)
    reset_for_tests()

    client = TestClient(create_app())
    response = client.get(
        "/wecom/kf/callback",
        params={
            "msg_signature": signature,
            "timestamp": timestamp,
            "nonce": nonce,
            "echostr": encrypted,
        },
    )

    assert response.status_code == 200
    assert response.text == plain


def test_wecom_kf_callback_rejects_bad_signature(app_env, monkeypatch) -> None:
    from app.database import reset_for_tests
    from app.main import create_app

    aes_key = b"1" * 32
    monkeypatch.setenv("WECOM_KF_TOKEN", "kf-token")
    monkeypatch.setenv("WECOM_KF_ENCODING_AES_KEY", base64.b64encode(aes_key).decode("ascii").rstrip("="))
    reset_for_tests()

    client = TestClient(create_app())
    response = client.get(
        "/wecom/kf/callback",
        params={
            "msg_signature": "bad",
            "timestamp": "1720000000",
            "nonce": "nonce",
            "echostr": encrypt_wecom_payload(aes_key, "hello", "ww123"),
        },
    )

    assert response.status_code == 403


def sign(token: str, timestamp: str, nonce: str, encrypted: str) -> str:
    return hashlib.sha1("".join(sorted([token, timestamp, nonce, encrypted])).encode("utf-8")).hexdigest()


def encrypt_wecom_payload(aes_key: bytes, message: str, receive_id: str) -> str:
    message_bytes = message.encode("utf-8")
    raw = b"abcdefghijklmnop" + struct.pack(">I", len(message_bytes)) + message_bytes + receive_id.encode("utf-8")
    padded = raw + pkcs7_padding(len(raw))
    encryptor = Cipher(algorithms.AES(aes_key), modes.CBC(aes_key[:16])).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("ascii")


def pkcs7_padding(size: int) -> bytes:
    pad = 32 - (size % 32)
    if pad == 0:
        pad = 32
    return bytes([pad]) * pad
