from rentivo.export.serializers import format_label


def test_xlsx_maps_to_excel():
    assert format_label("xlsx") == "Excel"


def test_csv_maps_to_csv_uppercase():
    assert format_label("csv") == "CSV"


def test_unknown_falls_back_to_uppercase():
    assert format_label("pdf") == "PDF"
