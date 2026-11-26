"""企业微信回调消息加解密（Token + EncodingAESKey）。"""

from __future__ import annotations

import base64
import hashlib
import socket
import struct
from typing import Iterable

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class WeComCryptoError(ValueError):
    """签名或解密失败。"""


def _sha1_hex(parts: Iterable[str]) -> str:
    raw = "".join(sorted(str(p) for p in parts))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def verify_wecom_signature(
    *,
    token: str,
    timestamp: str,
    nonce: str,
    encrypt: str,
    msg_signature: str,
) -> None:
    expected = _sha1_hex([token, timestamp, nonce, encrypt])
    if expected != str(msg_signature or "").strip().lower() and expected != str(msg_signature or "").strip():
        # 企微签名为小写 hex；兼容大小写
        if expected.lower() != str(msg_signature or "").strip().lower():
            raise WeComCryptoError("企微回调签名校验失败")


def _aes_key_from_encoding(encoding_aes_key: str) -> bytes:
    key = base64.b64decode(f"{encoding_aes_key.strip()}=")
    if len(key) != 32:
        raise WeComCryptoError("EncodingAESKey 无效")
    return key


def decrypt_wecom_cipher(
    *,
    encoding_aes_key: str,
    encrypt: str,
    receive_id: str,
) -> str:
    """解密 Encrypt 字段，返回明文 XML/JSON 字符串。"""
    aes_key = _aes_key_from_encoding(encoding_aes_key)
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(aes_key[:16]), backend=default_backend())
    decryptor = cipher.decryptor()
    plain = decryptor.update(base64.b64decode(encrypt)) + decryptor.finalize()
    pad = plain[-1]
    if isinstance(pad, str):
        pad = ord(pad)
    content = plain[:-pad]
    msg_len = socket.ntohl(struct.unpack("I", content[16:20])[0])
    xml = content[20 : 20 + msg_len].decode("utf-8")
    from_receive = content[20 + msg_len :].decode("utf-8")
    if receive_id and from_receive and from_receive != receive_id:
        raise WeComCryptoError("企微回调 receiveid 不匹配")
    return xml


def encrypt_wecom_plain(
    *,
    encoding_aes_key: str,
    plain: str,
    receive_id: str,
) -> str:
    """加密明文，返回 Encrypt 字符串（用于被动回复）。"""
    import os

    aes_key = _aes_key_from_encoding(encoding_aes_key)
    random16 = os.urandom(16)
    text = plain.encode("utf-8")
    receive = receive_id.encode("utf-8")
    msg_len = struct.pack("I", socket.htonl(len(text)))
    raw = random16 + msg_len + text + receive
    # PKCS#7
    amount = 32 - (len(raw) % 32)
    raw = raw + bytes([amount] * amount)
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(aes_key[:16]), backend=default_backend())
    encryptor = cipher.encryptor()
    return base64.b64encode(encryptor.update(raw) + encryptor.finalize()).decode("utf-8")


def build_wecom_encrypted_response(
    *,
    token: str,
    encoding_aes_key: str,
    receive_id: str,
    plain: str,
    nonce: str,
    timestamp: str,
) -> str:
    encrypt = encrypt_wecom_plain(
        encoding_aes_key=encoding_aes_key,
        plain=plain,
        receive_id=receive_id,
    )
    signature = _sha1_hex([token, timestamp, nonce, encrypt])
    return (
        "<xml>"
        f"<Encrypt><![CDATA[{encrypt}]]></Encrypt>"
        f"<MsgSignature><![CDATA[{signature}]]></MsgSignature>"
        f"<TimeStamp>{timestamp}</TimeStamp>"
        f"<Nonce><![CDATA[{nonce}]]></Nonce>"
        "</xml>"
    )
