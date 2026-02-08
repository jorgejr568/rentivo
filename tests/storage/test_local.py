from landlord.storage.local import LocalStorage


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
        storage = LocalStorage(str(new_dir))
        assert new_dir.exists()

    def test_save_nested_path(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        storage.save("a/b/c/file.pdf", b"data")
        assert (tmp_path / "a" / "b" / "c" / "file.pdf").exists()
