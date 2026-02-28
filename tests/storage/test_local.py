from rentivo.storage.local import LocalStorage


class TestLocalStorage:
    def test_save_creates_file(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        path = storage.save("test/file.pdf", b"pdf-content")

        assert (tmp_path / "test" / "file.pdf").exists()
        assert (tmp_path / "test" / "file.pdf").read_bytes() == b"pdf-content"
        assert path == str((tmp_path / "test" / "file.pdf").resolve())

    def test_get_url_returns_path(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        url = storage.get_url("test/file.pdf")
        assert url == str((tmp_path / "test" / "file.pdf").resolve())

    def test_creates_base_dir(self, tmp_path):
        new_dir = tmp_path / "new_dir"
        LocalStorage(str(new_dir))
        assert new_dir.exists()

    def test_save_nested_path(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        storage.save("a/b/c/file.pdf", b"data")
        assert (tmp_path / "a" / "b" / "c" / "file.pdf").exists()

    def test_get_returns_file_data(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        storage.save("test/file.pdf", b"hello-pdf")
        data = storage.get("test/file.pdf")
        assert data == b"hello-pdf"

    def test_save_with_content_type(self, tmp_path):
        """content_type param is accepted but ignored for local storage."""
        storage = LocalStorage(str(tmp_path))
        storage.save("test/img.jpg", b"jpeg-data", content_type="image/jpeg")
        assert (tmp_path / "test" / "img.jpg").exists()
        assert (tmp_path / "test" / "img.jpg").read_bytes() == b"jpeg-data"
