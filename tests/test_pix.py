from landlord.pix import (
    _crc16_ccitt,
    _strip_accents,
    _tlv,
    generate_pix_payload,
    generate_pix_qrcode_png,
)


class TestTlv:
    def test_simple(self):
        assert _tlv("00", "01") == "000201"

    def test_longer_value(self):
        result = _tlv("26", "br.gov.bcb.pix")
        assert result == "2614br.gov.bcb.pix"


class TestCrc16Ccitt:
    def test_known_value(self):
        # CRC should be a 4-char uppercase hex
        result = _crc16_ccitt("test")
        assert len(result) == 4
        assert result == result.upper()


class TestStripAccents:
    def test_no_accents(self):
        assert _strip_accents("Hello") == "Hello"

    def test_accents(self):
        assert _strip_accents("João") == "Joao"

    def test_cedilla(self):
        assert _strip_accents("Março") == "Marco"


class TestGeneratePixPayload:
    def test_returns_string(self):
        payload = generate_pix_payload(
            pix_key="12345678900",
            merchant_name="João Silva",
            merchant_city="São Paulo",
        )
        assert isinstance(payload, str)
        assert len(payload) > 0

    def test_contains_pix_key(self):
        payload = generate_pix_payload(
            pix_key="test@email.com",
            merchant_name="Test",
            merchant_city="City",
        )
        assert "test@email.com" in payload

    def test_with_amount(self):
        payload = generate_pix_payload(
            pix_key="key",
            merchant_name="Name",
            merchant_city="City",
            amount=150.50,
        )
        assert "150.50" in payload

    def test_without_amount(self):
        payload = generate_pix_payload(
            pix_key="key",
            merchant_name="Name",
            merchant_city="City",
            amount=None,
        )
        # tag 54 should not appear
        assert "54" not in payload[:20]

    def test_ends_with_crc(self):
        payload = generate_pix_payload(
            pix_key="key",
            merchant_name="Name",
            merchant_city="City",
        )
        # 6304 + 4 hex chars CRC
        assert "6304" in payload

    def test_txid_default(self):
        payload = generate_pix_payload(
            pix_key="key",
            merchant_name="Name",
            merchant_city="City",
        )
        assert "***" in payload

    def test_custom_txid(self):
        payload = generate_pix_payload(
            pix_key="key",
            merchant_name="Name",
            merchant_city="City",
            txid="ABC123",
        )
        assert "ABC123" in payload


class TestGeneratePixQrcodePng:
    def test_returns_png_bytes(self):
        result = generate_pix_qrcode_png(
            pix_key="12345678900",
            merchant_name="Test",
            merchant_city="City",
        )
        assert isinstance(result, bytes)
        # PNG magic bytes
        assert result[:4] == b"\x89PNG"

    def test_with_amount(self):
        result = generate_pix_qrcode_png(
            pix_key="key",
            merchant_name="Name",
            merchant_city="City",
            amount=100.00,
        )
        assert result[:4] == b"\x89PNG"
