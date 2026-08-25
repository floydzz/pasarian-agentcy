import pytest

from app.media.storage import MEDIA_PREFIX, AssetStorage


def test_save_returns_a_servable_url(tmp_path):
    url = AssetStorage(tmp_path).save(b"bytes")
    assert url.startswith(f"{MEDIA_PREFIX}/")
    assert url.endswith(".png")


def test_saved_bytes_come_back(tmp_path):
    storage = AssetStorage(tmp_path)
    url = storage.save(b"bytes")
    assert storage.read(url) == b"bytes"


def test_two_saves_never_collide(tmp_path):
    storage = AssetStorage(tmp_path)
    assert storage.save(b"a") != storage.save(b"b")


def test_creates_its_directory_on_demand(tmp_path):
    AssetStorage(tmp_path / "nested" / "deeper").save(b"bytes")
    assert (tmp_path / "nested" / "deeper").is_dir()


def test_refuses_a_url_outside_the_media_prefix(tmp_path):
    with pytest.raises(ValueError, match="not a media url"):
        AssetStorage(tmp_path).path_for("/etc/passwd")


def test_refuses_to_traverse_out_of_the_root(tmp_path):
    with pytest.raises(ValueError, match="not a media url"):
        AssetStorage(tmp_path).path_for(f"{MEDIA_PREFIX}/../../etc/passwd")
