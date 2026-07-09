from __future__ import annotations

import base64
import hashlib
import struct
import xml.etree.ElementTree as ET

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import APIRouter, HTTPException, Query, Request, Response

from .config import get_settings


router = APIRouter(prefix="/wecom/kf", tags=["wecom-kf"])


@router.get("/callback")
def verify_callback(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
) -> Response:
    settings = get_settings()
    if not settings.wecom_kf_token or not settings.wecom_kf_encoding_aes_key:
        raise HTTPException(status_code=503, detail="WeCom customer service callback is not configured")

    plain = decrypt_wecom_payload(
        token=settings.wecom_kf_token,
        encoding_aes_key=settings.wecom_kf_encoding_aes_key,
        msg_signature=msg_signature,
        timestamp=timestamp,
        nonce=nonce,
        encrypted=echostr,
        expected_receive_id=settings.wecom_corp_id,
    )
    return Response(content=plain, media_type="text/plain")


@router.post("/callback")
async def receive_callback(request: Request) -> Response:
    # Keep the first deploy lightweight: acknowledging callbacks lets WeCom
    # finish setup. The real message pull/decrypt loop can be added next.
    await request.body()
    return Response(content="success", media_type="text/plain")


def decrypt_wecom_payload(
    *,
    token: str,
    encoding_aes_key: str,
    msg_signature: str,
    timestamp: str,
    nonce: str,
    encrypted: str,
    expected_receive_id: str = "",
) -> str:
    verify_signature(token, timestamp, nonce, encrypted, msg_signature)
    aes_key = decode_aes_key(encoding_aes_key)
    raw_plain = aes_cbc_decrypt(aes_key, encrypted)
    plain, receive_id = parse_plaintext(raw_plain)
    if expected_receive_id and receive_id and receive_id != expected_receive_id:
        raise HTTPException(status_code=400, detail="invalid receive id")
    return plain


def verify_signature(token: str, timestamp: str, nonce: str, encrypted: str, msg_signature: str) -> None:
    expected = hashlib.sha1("".join(sorted([token, timestamp, nonce, encrypted])).encode("utf-8")).hexdigest()
    if expected != msg_signature:
        raise HTTPException(status_code=403, detail="invalid WeCom callback signature")


def decode_aes_key(encoding_aes_key: str) -> bytes:
    try:
        aes_key = base64.b64decode(f"{encoding_aes_key}=", validate=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="invalid EncodingAESKey") from exc
    if len(aes_key) != 32:
        raise HTTPException(status_code=500, detail="invalid EncodingAESKey length")
    return aes_key


def aes_cbc_decrypt(aes_key: bytes, encrypted: str) -> bytes:
    try:
        ciphertext = base64.b64decode(encrypted, validate=True)
        decryptor = Cipher(algorithms.AES(aes_key), modes.CBC(aes_key[:16])).decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        return remove_pkcs7_padding(padded)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid encrypted payload") from exc


def remove_pkcs7_padding(data: bytes) -> bytes:
    if not data:
        raise HTTPException(status_code=400, detail="empty encrypted payload")
    pad = data[-1]
    if pad < 1 or pad > 32:
        raise HTTPException(status_code=400, detail="invalid encrypted payload padding")
    if data[-pad:] != bytes([pad]) * pad:
        raise HTTPException(status_code=400, detail="invalid encrypted payload padding")
    return data[:-pad]


def parse_plaintext(raw_plain: bytes) -> tuple[str, str]:
    if len(raw_plain) < 20:
        raise HTTPException(status_code=400, detail="invalid encrypted payload body")
    msg_len = struct.unpack(">I", raw_plain[16:20])[0]
    msg_start = 20
    msg_end = msg_start + msg_len
    if msg_end > len(raw_plain):
        raise HTTPException(status_code=400, detail="invalid encrypted payload length")
    message = raw_plain[msg_start:msg_end].decode("utf-8")
    receive_id = raw_plain[msg_end:].decode("utf-8")
    return message, receive_id


def extract_encrypt_from_xml(body: str) -> str:
    root = ET.fromstring(body)
    node = root.find("Encrypt")
    return node.text if node is not None and node.text is not None else ""
