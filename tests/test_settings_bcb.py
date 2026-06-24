from rentivo.settings import Settings


def test_bcb_sgs_base_url_default():
    s = Settings(_env_file=None)
    assert s.bcb_sgs_base_url == "https://api.bcb.gov.br"


def test_bcb_sgs_base_url_override(monkeypatch):
    monkeypatch.setenv("RENTIVO_BCB_SGS_BASE_URL", "http://localhost:9999")
    s = Settings(_env_file=None)
    assert s.bcb_sgs_base_url == "http://localhost:9999"
