"""PIX BR Code payload generator following BCB EMV QR Code specification.

Generates the payload string for a static PIX QR code and renders it as a PNG image.
"""

from __future__ import annotations

from io import BytesIO

import qrcode
from qrcode.image.pil import PilImage


def _tlv(tag: str, value: str) -> str:
    """Build a TLV (Tag-Length-Value) field."""
    return f"{tag}{len(value):02d}{value}"


def _crc16_ccitt(data: str) -> str:
    """Compute CRC16-CCITT (0xFFFF) over the payload string."""
    crc = 0xFFFF
    for byte in data.encode("ascii"):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def generate_pix_payload(
    *,
    pix_key: str,
    merchant_name: str,
    merchant_city: str,
    amount: float | None = None,
    txid: str = "***",
) -> str:
    """Generate a PIX BR Code payload string.

    Args:
        pix_key: The PIX key (CPF, CNPJ, phone, email, or random key).
        merchant_name: Recipient name (max 25 chars, ASCII only).
        merchant_city: Recipient city (max 15 chars, ASCII only).
        amount: Transaction amount in reais (e.g. 150.50). None for open amount.
        txid: Transaction ID (default "***").

    Returns:
        The complete BR Code payload string with CRC16.
    """
    # Strip accents for ASCII-only fields
    name = _strip_accents(merchant_name)[:25]
    city = _strip_accents(merchant_city)[:15]

    # Merchant Account Information (tag 26)
    mai = _tlv("00", "br.gov.bcb.pix") + _tlv("01", pix_key)
    # Additional Data Field Template (tag 62)
    adft = _tlv("05", txid)

    payload = (
        _tlv("00", "01")  # Payload Format Indicator
        + _tlv("26", mai)  # Merchant Account Information
        + _tlv("52", "0000")  # Merchant Category Code
        + _tlv("53", "986")  # Transaction Currency (BRL)
    )

    if amount is not None and amount > 0:
        payload += _tlv("54", f"{amount:.2f}")

    payload += (
        _tlv("58", "BR")  # Country Code
        + _tlv("59", name)  # Merchant Name
        + _tlv("60", city)  # Merchant City
        + _tlv("62", adft)  # Additional Data
    )

    # CRC16 placeholder: tag "63" + length "04" + actual CRC
    payload += "6304"
    crc = _crc16_ccitt(payload)
    payload += crc

    return payload


def _strip_accents(text: str) -> str:
    """Remove accents for ASCII-safe PIX payload fields."""
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def generate_pix_qrcode_png(
    *,
    pix_key: str,
    merchant_name: str,
    merchant_city: str,
    amount: float | None = None,
    txid: str = "***",
    box_size: int = 10,
    border: int = 2,
    payload: str = "",
) -> bytes:
    """Generate a PIX QR code as PNG bytes.

    Args:
        payload: Pre-computed payload string. If empty, generates one from the other args.

    Returns:
        PNG image bytes ready to be saved or embedded in a PDF.
    """
    if not payload:
        payload = generate_pix_payload(
            pix_key=pix_key,
            merchant_name=merchant_name,
            merchant_city=merchant_city,
            amount=amount,
            txid=txid,
        )

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    img: PilImage = qr.make_image(fill_color="black", back_color="white")

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
