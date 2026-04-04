from __future__ import annotations

import tempfile

from imgui_bundle_esc_config.firmware_catalog import FirmwareCatalogClient, FirmwareRelease, describe_release_compatibility


def test_catalog_client_parses_bluejay_github_releases() -> None:
    payload = [
        {
            "tag_name": "v0.8",
            "name": "0.8",
            "assets": [{"name": "ignored.hex"}],
            "prerelease": False,
            "published_at": "2024-01-01T00:00:00Z",
        },
        {
            "tag_name": "v0.21.0",
            "name": "0.21.0",
            "assets": [{"name": "A_H_120_48_v0.21.0.hex", "browser_download_url": "https://example.invalid/A_H_120_48_v0.21.0.hex"}],
            "prerelease": False,
            "published_at": "2024-02-01T00:00:00Z",
        },
        {
            "tag_name": "v0.22.0-beta",
            "name": "0.22.0-beta",
            "assets": [{"name": "A_H_120_48_v0.22.0-beta.hex", "browser_download_url": "https://example.invalid/A_H_120_48_v0.22.0-beta.hex"}],
            "prerelease": True,
            "published_at": "2024-03-01T00:00:00Z",
        },
        {
            "tag_name": "v0.23.0",
            "name": "0.23.0",
            "assets": [],
            "prerelease": False,
            "published_at": "2024-04-01T00:00:00Z",
        },
    ]

    client = FirmwareCatalogClient(fetch_json=lambda _url: payload)
    snapshot = client.refresh_catalog()

    bluejay = snapshot.releases_by_source["Bluejay"]
    assert [release.key for release in bluejay] == ["v0.21.0", "v0.22.0-beta"]
    assert bluejay[0].download_url_template.endswith("/v0.21.0/")
    assert bluejay[0].assets[0][0] == "A_H_120_48_v0.21.0.hex"
    assert bluejay[1].prerelease is True


def test_catalog_client_includes_static_blheli_s_entries() -> None:
    client = FirmwareCatalogClient(fetch_json=lambda _url: [])
    snapshot = client.refresh_catalog()

    blheli_s = snapshot.releases_by_source["BLHeli_S"]
    assert len(blheli_s) >= 4
    assert blheli_s[0].family == "BLHeli_S"
    assert "{0}" in blheli_s[0].download_url_template


def test_catalog_client_downloads_bluejay_asset_into_cache() -> None:
    payload = [
        {
            "tag_name": "v0.21.0",
            "name": "0.21.0",
            "assets": [
                {
                    "name": "A_H_120_48_v0.21.0.hex",
                    "browser_download_url": "https://example.invalid/A_H_120_48_v0.21.0.hex",
                }
            ],
            "prerelease": False,
            "published_at": "2024-02-01T00:00:00Z",
        }
    ]
    firmware_hex = b":0400000001020304F2\n:00000001FF\n"
    fetched_urls: list[str] = []

    def fetch_bytes(url: str) -> bytes:
        fetched_urls.append(url)
        return firmware_hex

    with tempfile.TemporaryDirectory() as temp_dir:
        client = FirmwareCatalogClient(fetch_json=lambda _url: payload, fetch_bytes=fetch_bytes, cache_dir=temp_dir)
        release = client.refresh_catalog().releases_by_source["Bluejay"][0]

        image = client.download_release_image(release, layout_name="A_H_120", pwm_khz=48)

        assert image.family == "Bluejay"
        assert image.name == "A_H_120_48_v0.21.0.hex"
        assert image.origin == "downloaded"
        assert image.start_address == 0
        assert image.data == b"\x01\x02\x03\x04"
        assert fetched_urls == ["https://example.invalid/A_H_120_48_v0.21.0.hex"]


def test_catalog_client_resolves_blheli_s_template_download() -> None:
    fetched_urls: list[str] = []

    def fetch_bytes(url: str) -> bytes:
        fetched_urls.append(url)
        return b":040000000A0B0C0DCE\n:00000001FF\n"

    with tempfile.TemporaryDirectory() as temp_dir:
        client = FirmwareCatalogClient(fetch_json=lambda _url: [], fetch_bytes=fetch_bytes, cache_dir=temp_dir)
        release = client.refresh_catalog().releases_by_source["BLHeli_S"][0]

        image = client.download_release_image(release, layout_name="#A_H_30#")

        assert image.family == "BLHeli_S"
        assert image.name.endswith("A_H_30_REV16_7.HEX")
        assert image.data == b"\x0A\x0B\x0C\x0D"
        assert "A_H_30" in fetched_urls[0]


def test_describe_release_compatibility_matches_bluejay_asset() -> None:
    release = FirmwareRelease(
        source="Bluejay",
        family="Bluejay",
        key="v0.21.0",
        name="0.21.0",
        download_url_template="https://example.invalid/bluejay/",
        assets=(("A_H_120_48_v0.21.0.hex", "https://example.invalid/A_H_120_48_v0.21.0.hex"),),
    )

    compatibility = describe_release_compatibility(
        release,
        esc_family="Bluejay",
        layout_name="A_H_120",
        pwm_khz=48,
    )

    assert compatibility.compatible is True
    assert compatibility.asset_name == "A_H_120_48_v0.21.0.hex"


def test_describe_release_compatibility_rejects_missing_bluejay_layout_variant() -> None:
    release = FirmwareRelease(
        source="Bluejay",
        family="Bluejay",
        key="v0.21.0",
        name="0.21.0",
        download_url_template="https://example.invalid/bluejay/",
        assets=(("A_H_120_48_v0.21.0.hex", "https://example.invalid/A_H_120_48_v0.21.0.hex"),),
    )

    compatibility = describe_release_compatibility(
        release,
        esc_family="Bluejay",
        layout_name="A_H_15",
        pwm_khz=48,
    )

    assert compatibility.compatible is False
    assert "No Bluejay asset" in compatibility.reason


# ---------------------------------------------------------------------------
# Offline snapshot persistence tests
# ---------------------------------------------------------------------------

_MINIMAL_PAYLOAD = [
    {
        "tag_name": "v0.21.0",
        "name": "0.21.0",
        "assets": [{"name": "A_H_120_48_v0.21.0.hex", "browser_download_url": "https://example.invalid/A_H_120_48_v0.21.0.hex"}],
        "prerelease": False,
        "published_at": "2024-02-01T00:00:00Z",
    }
]


def test_catalog_saves_snapshot_file_after_successful_refresh() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        client = FirmwareCatalogClient(fetch_json=lambda _url: _MINIMAL_PAYLOAD, cache_dir=temp_dir)
        client.refresh_catalog()

        import pathlib
        snapshot_file = pathlib.Path(temp_dir) / "catalog_snapshot.json"
        assert snapshot_file.exists(), "Snapshot file should be written after successful refresh"
        import json
        data = json.loads(snapshot_file.read_text())
        assert "Bluejay" in data["releases_by_source"]
        releases = data["releases_by_source"]["Bluejay"]
        assert len(releases) == 1
        assert releases[0]["key"] == "v0.21.0"


def test_catalog_loads_offline_fallback_when_network_fails() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        # First: successful refresh to save snapshot
        client = FirmwareCatalogClient(fetch_json=lambda _url: _MINIMAL_PAYLOAD, cache_dir=temp_dir)
        client.refresh_catalog()

        # Second: network fails — should fall back to cached snapshot
        def bad_fetch(_url: str) -> object:
            raise OSError("simulated network failure")

        offline_client = FirmwareCatalogClient(fetch_json=bad_fetch, cache_dir=temp_dir)
        snapshot = offline_client.refresh_catalog()

        assert snapshot is not None
        bluejay = snapshot.releases_by_source.get("Bluejay", ())
        assert len(bluejay) == 1
        assert bluejay[0].key == "v0.21.0"


def test_catalog_reraises_when_network_fails_and_no_cache() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        def bad_fetch(_url: str) -> object:
            raise ConnectionError("no network")

        client = FirmwareCatalogClient(fetch_json=bad_fetch, cache_dir=temp_dir)

        import pytest
        with pytest.raises(ConnectionError, match="no network"):
            client.refresh_catalog()


def test_load_catalog_snapshot_returns_none_when_no_file() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        client = FirmwareCatalogClient(fetch_json=lambda _url: [], cache_dir=temp_dir)
        assert client.load_catalog_snapshot() is None


def test_load_catalog_snapshot_returns_none_on_corrupt_json() -> None:
    import pathlib
    with tempfile.TemporaryDirectory() as temp_dir:
        snapshot_path = pathlib.Path(temp_dir, "catalog_snapshot.json")
        snapshot_path.write_text("{ invalid json !!!", encoding="utf-8")
        client = FirmwareCatalogClient(fetch_json=lambda _url: [], cache_dir=temp_dir)
        assert client.load_catalog_snapshot() is None
        assert client.last_snapshot_load_error
        quarantined = list(pathlib.Path(temp_dir).glob("catalog_snapshot.corrupt.*.json"))
        assert quarantined, "Corrupt snapshot should be quarantined for recovery/debugging"
        assert snapshot_path.exists() is False


def test_catalog_refresh_reraises_when_offline_and_only_corrupt_cache_exists() -> None:
    import pathlib
    with tempfile.TemporaryDirectory() as temp_dir:
        pathlib.Path(temp_dir, "catalog_snapshot.json").write_text("{ invalid json !!!", encoding="utf-8")

        def bad_fetch(_url: str) -> object:
            raise OSError("offline")

        client = FirmwareCatalogClient(fetch_json=bad_fetch, cache_dir=temp_dir)

        import pytest
        with pytest.raises(OSError, match="offline"):
            client.refresh_catalog()
        assert client.last_refresh_used_cache is False
        assert client.last_snapshot_load_error


def test_save_and_load_catalog_snapshot_round_trip() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        client = FirmwareCatalogClient(fetch_json=lambda _url: _MINIMAL_PAYLOAD, cache_dir=temp_dir)
        original = client.refresh_catalog()
        loaded = client.load_catalog_snapshot()

        assert loaded is not None
        assert loaded.releases_by_source.keys() == original.releases_by_source.keys()
        bluejay_orig = original.releases_by_source["Bluejay"]
        bluejay_loaded = loaded.releases_by_source["Bluejay"]
        assert len(bluejay_loaded) == len(bluejay_orig)
        r_orig = bluejay_orig[0]
        r_loaded = bluejay_loaded[0]
        assert r_loaded.key == r_orig.key
        assert r_loaded.name == r_orig.name
        assert r_loaded.assets == r_orig.assets
        assert r_loaded.prerelease == r_orig.prerelease


def test_catalog_refresh_sets_last_refresh_used_cache_true_on_fallback() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        warm_client = FirmwareCatalogClient(fetch_json=lambda _url: _MINIMAL_PAYLOAD, cache_dir=temp_dir)
        _ = warm_client.refresh_catalog()

        def bad_fetch(_url: str) -> object:
            raise OSError("offline")

        client = FirmwareCatalogClient(fetch_json=bad_fetch, cache_dir=temp_dir)
        _ = client.refresh_catalog()
        assert client.last_refresh_used_cache is True


def test_catalog_refresh_sets_last_refresh_used_cache_false_on_live_success() -> None:
    client = FirmwareCatalogClient(fetch_json=lambda _url: _MINIMAL_PAYLOAD)
    _ = client.refresh_catalog()
    assert client.last_refresh_used_cache is False
