import pytest

from rentivo.storage.local import LocalStorage


class TestLocalStoragePathTraversal:
    def test_save_rejects_traversal(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        with pytest.raises(ValueError):
            storage.save("../outside.pdf", b"data")

    def test_get_rejects_traversal(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        with pytest.raises(ValueError):
            storage.get("../../etc/passwd")

    def test_get_url_rejects_traversal(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        with pytest.raises(ValueError):
            storage.get_url("../../etc/passwd")

    def test_delete_removes_file(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        storage.save("a/file.pdf", b"data")
        assert (tmp_path / "a" / "file.pdf").exists()
        storage.delete("a/file.pdf")
        assert not (tmp_path / "a" / "file.pdf").exists()

    def test_delete_missing_key_is_noop(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        storage.delete("does-not-exist.pdf")  # should not raise

    def test_delete_refuses_unsafe_key(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        storage.delete("../outside.pdf")  # logs warning, no raise

    def test_get_ref_rejects_traversal(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        with pytest.raises(ValueError):
            storage.get_ref("../../etc/passwd")


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

    def test_get_ref_returns_local_kind_with_resolved_path(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        ref = storage.get_ref("test/file.pdf")
        assert ref.kind == "local"
        assert ref.location == str((tmp_path / "test" / "file.pdf").resolve())

    def test_get_ref_accepts_absolute_path_under_base_dir(self, tmp_path):
        """Legacy local rows store the resolved absolute path in pdf_path."""
        storage = LocalStorage(str(tmp_path))
        absolute = str((tmp_path / "a" / "file.pdf").resolve())
        ref = storage.get_ref(absolute)
        assert ref.kind == "local"
        assert ref.location == absolute

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
