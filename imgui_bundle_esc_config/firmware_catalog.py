"""Firmware catalog models and client for the ImGui ESC configurator.

Initial scope:
- Bluejay release discovery from GitHub releases metadata
- BLHeli_S static version list matching the web reference's bundled catalog
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Callable
from urllib.request import urlopen


BLUEJAY_RELEASES_URL = "https://api.github.com/repos/bird-sanctuary/bluejay/releases?per_page=100&page=1"
BLUEJAY_BLACKLIST = {"v0.8"}

BLHELI_S_RELEASES: tuple[dict[str, str], ...] = (
    {
        "name": "16.7 [Official] - latest master",
        "url": "https://raw.githubusercontent.com/bitdump/BLHeli/master/BLHeli_S SiLabs/Hex files/{0}_REV16_7.HEX",
        "key": "16.7-master",
    },
    {
        "name": "16.71 [Official, beta]",
        "url": "https://raw.githubusercontent.com/bitdump/BLHeli/b73b9b91564fb1104eaf26261c02e38d5eeab68f/BLHeli_S SiLabs/Hex files  16.71/{0}_REV16_71.HEX",
        "key": "16.71",
    },
    {
        "name": "16.7 [Official]",
        "url": "https://raw.githubusercontent.com/bitdump/BLHeli/00e67de2ac769ea26150780b6edf9e5021ef917b/BLHeli_S SiLabs/Hex files/{0}_REV16_7.HEX",
        "key": "16.7",
    },
    {
        "name": "16.6 [Official]",
        "url": "https://raw.githubusercontent.com/bitdump/BLHeli/a873f7c963af3138aa3225e6ca929442bcfeab6c/BLHeli_S SiLabs/Hex files/{0}_REV16_6.HEX",
        "key": "16.6",
    },
)


@dataclass(frozen=True)
class FirmwareRelease:
    source: str
    family: str
    key: str
    name: str
    download_url_template: str
    release_url: str | None = None
    prerelease: bool = False
    published_at: str = ""
    assets: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class FirmwareLayout:
    source: str
    key: str
    name: str


@dataclass(frozen=True)
class FirmwareImage:
    source: str
    family: str
    name: str
    data: bytes
    origin: str
    start_address: int = 0
    path: str = ""


@dataclass(frozen=True)
class FirmwareCatalogSnapshot:
    refreshed_at: str
    releases_by_source: dict[str, tuple[FirmwareRelease, ...]] = field(default_factory=dict)
    layouts_by_source: dict[str, tuple[FirmwareLayout, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class FirmwareCompatibility:
    compatible: bool
    reason: str
    layout_token: str = ""
    asset_name: str = ""


def _load_firmware_data(
    raw: bytes,
    *,
    name: str,
    family: str = "",
    source: str = "",
    origin: str,
    path: str = "",
) -> FirmwareImage:
    suffix = Path(name).suffix.lower()
    if suffix == ".hex" or raw.lstrip().startswith(b":"):
        start_address, image_data = _parse_intel_hex(raw)
    else:
        start_address, image_data = 0, raw

    if not image_data:
        raise ValueError(f"Firmware image '{name}' did not contain any flash data")

    return FirmwareImage(
        source=source,
        family=family,
        name=name,
        data=image_data,
        origin=origin,
        start_address=start_address,
        path=path,
    )


def _normalize_layout_token(layout_name: str) -> str:
    cleaned = (layout_name or "").strip().strip("#")
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned.upper()


def _safe_cache_component(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", value.strip())
    return cleaned.strip("._") or "firmware"


def describe_release_compatibility(
    release: FirmwareRelease,
    *,
    esc_family: str,
    layout_name: str,
    pwm_khz: int | None = None,
) -> FirmwareCompatibility:
    target_family = (esc_family or "").strip()
    layout_token = _normalize_layout_token(layout_name)

    if not target_family:
        return FirmwareCompatibility(False, "Read settings to identify the ESC family")
    if release.family != target_family:
        return FirmwareCompatibility(False, f"Family mismatch: target={target_family}, release={release.family}")
    if not layout_token:
        return FirmwareCompatibility(False, "Read settings to identify the ESC layout")

    if release.family == "BLHeli_S":
        return FirmwareCompatibility(True, f"Compatible with layout {layout_token}", layout_token=layout_token)

    if release.family == "Bluejay":
        pwm_value = int(pwm_khz) if pwm_khz is not None else 48
        if pwm_value not in {24, 48, 96}:
            return FirmwareCompatibility(False, "Bluejay requires a PWM selection of 24, 48, or 96 kHz", layout_token=layout_token)
        expected_name = f"{layout_token}_{pwm_value}_{release.key}.hex"
        if release.assets:
            for asset_name, _asset_url in release.assets:
                if asset_name.lower() == expected_name.lower():
                    return FirmwareCompatibility(True, f"Asset match for {layout_token} @ {pwm_value} kHz", layout_token=layout_token, asset_name=asset_name)
            return FirmwareCompatibility(False, f"No Bluejay asset for {layout_token} @ {pwm_value} kHz", layout_token=layout_token)
        return FirmwareCompatibility(False, "Release metadata does not include Bluejay asset details", layout_token=layout_token)

    return FirmwareCompatibility(False, f"Unsupported firmware family: {release.family}", layout_token=layout_token)


def _parse_intel_hex(data: bytes) -> tuple[int, bytes]:
    text = data.decode("utf-8", errors="replace")
    memory: dict[int, int] = {}
    upper_address = 0

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise ValueError(f"Invalid Intel HEX record at line {line_number}: missing ':' prefix")

        record = bytes.fromhex(line[1:])
        if len(record) < 5:
            raise ValueError(f"Invalid Intel HEX record at line {line_number}: too short")

        byte_count = record[0]
        if len(record) != byte_count + 5:
            raise ValueError(f"Invalid Intel HEX record at line {line_number}: length mismatch")

        address = (record[1] << 8) | record[2]
        record_type = record[3]
        payload = record[4:4 + byte_count]
        checksum = record[-1]
        checksum_total = (sum(record[:-1]) + checksum) & 0xFF
        if checksum_total != 0:
            raise ValueError(f"Invalid Intel HEX checksum at line {line_number}")

        if record_type == 0x00:
            absolute_address = upper_address + address
            for offset, value in enumerate(payload):
                memory[absolute_address + offset] = value
        elif record_type == 0x01:
            break
        elif record_type == 0x04:
            if len(payload) != 2:
                raise ValueError(f"Invalid Intel HEX extended linear address record at line {line_number}")
            upper_address = ((payload[0] << 8) | payload[1]) << 16
        elif record_type in {0x02, 0x03, 0x05}:
            continue
        else:
            raise ValueError(f"Unsupported Intel HEX record type 0x{record_type:02X} at line {line_number}")

    if not memory:
        return 0, b""

    min_address = min(memory)
    max_address = max(memory)
    blob = bytearray([0xFF] * (max_address - min_address + 1))
    for address, value in memory.items():
        blob[address - min_address] = value
    return min_address, bytes(blob)


def load_firmware_file(path: str, *, family: str = "", source: str = "Local File") -> FirmwareImage:
    file_path = Path(path).expanduser()
    raw = file_path.read_bytes()
    return _load_firmware_data(
        raw,
        name=file_path.name,
        family=family,
        source=source,
        origin="local-file",
        path=str(file_path),
    )


def _default_fetch_json(url: str) -> object:
    with urlopen(url, timeout=10) as response:  # noqa: S310 - fixed trusted metadata URLs for tool use
        return json.loads(response.read().decode("utf-8"))


def _default_fetch_bytes(url: str) -> bytes:
    with urlopen(url, timeout=20) as response:  # noqa: S310 - fixed trusted metadata URLs for tool use
        return response.read()


class FirmwareCatalogClient:
    def __init__(
        self,
        fetch_json: Callable[[str], object] | None = None,
        fetch_bytes: Callable[[str], bytes] | None = None,
        cache_dir: str | None = None,
    ) -> None:
        self._fetch_json = fetch_json or _default_fetch_json
        self._fetch_bytes = fetch_bytes or _default_fetch_bytes
        self._cache_dir = Path(cache_dir).expanduser() if cache_dir else Path.home() / ".cache" / "pico-msp-bridge" / "esc-configurator" / "firmware"
        self.last_refresh_used_cache = False
        self.last_snapshot_load_error: str | None = None

    def _get_cache_dir(self) -> Path:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        return self._cache_dir

    def _resolve_release_download(self, release: FirmwareRelease, *, layout_name: str, pwm_khz: int | None = None) -> tuple[str, str]:
        layout_token = _normalize_layout_token(layout_name)
        if not layout_token:
            raise ValueError("A target ESC layout must be known before downloading firmware")

        if release.family == "BLHeli_S":
            url = release.download_url_template.format(layout_token)
            return url, Path(url).name

        if release.family == "Bluejay":
            pwm_value = int(pwm_khz) if pwm_khz is not None else 48
            if pwm_value not in {24, 48, 96}:
                raise ValueError("Bluejay downloads require a PWM selection of 24, 48, or 96 kHz")
            preferred_name = f"{layout_token}_{pwm_value}_{release.key}.hex"
            if release.assets:
                for asset_name, asset_url in release.assets:
                    if asset_name.lower() == preferred_name.lower():
                        return asset_url, asset_name
                for asset_name, asset_url in release.assets:
                    normalized_name = asset_name.upper()
                    if normalized_name.startswith(f"{layout_token}_{pwm_value}_") and normalized_name.endswith(".HEX"):
                        return asset_url, asset_name
            return release.download_url_template + preferred_name, preferred_name

        raise ValueError(f"Unsupported firmware family for download: {release.family}")

    def download_release_image(self, release: FirmwareRelease, *, layout_name: str, pwm_khz: int | None = None) -> FirmwareImage:
        url, filename = self._resolve_release_download(release, layout_name=layout_name, pwm_khz=pwm_khz)
        cache_path = self._get_cache_dir() / _safe_cache_component(release.source) / _safe_cache_component(release.key) / filename
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        if cache_path.exists() and cache_path.stat().st_size > 0:
            raw = cache_path.read_bytes()
        else:
            raw = self._fetch_bytes(url)
            cache_path.write_bytes(raw)

        return _load_firmware_data(
            raw,
            name=filename,
            family=release.family,
            source=release.source,
            origin="downloaded",
            path=str(cache_path),
        )

    def refresh_catalog(self) -> FirmwareCatalogSnapshot:
        try:
            bluejay_releases = self._get_bluejay_releases()
            blheli_s_releases = self._get_blheli_s_releases()
        except Exception:
            cached = self.load_catalog_snapshot()
            if cached is not None:
                self.last_refresh_used_cache = True
                return cached
            self.last_refresh_used_cache = False
            raise

        snapshot = FirmwareCatalogSnapshot(
            refreshed_at=datetime.now(timezone.utc).isoformat(),
            releases_by_source={
                "Bluejay": tuple(bluejay_releases),
                "BLHeli_S": tuple(blheli_s_releases),
            },
            layouts_by_source={
                "Bluejay": (),
                "BLHeli_S": (),
            },
        )
        self.save_catalog_snapshot(snapshot)
        self.last_refresh_used_cache = False
        return snapshot

    _CATALOG_CACHE_FILE = "catalog_snapshot.json"

    def _catalog_snapshot_path(self) -> Path:
        return self._get_cache_dir() / self._CATALOG_CACHE_FILE

    def _quarantine_corrupt_snapshot(self, path: Path) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        quarantine_path = path.with_name(f"{path.stem}.corrupt.{timestamp}{path.suffix}")
        try:
            path.rename(quarantine_path)
        except OSError:
            # Best-effort only; if this fails, keep behavior non-fatal.
            pass

    def save_catalog_snapshot(self, snapshot: FirmwareCatalogSnapshot) -> None:
        """Persist a catalog snapshot to disk for offline fallback."""
        try:
            def _release_to_dict(r: FirmwareRelease) -> dict:
                return {
                    "source": r.source,
                    "family": r.family,
                    "key": r.key,
                    "name": r.name,
                    "download_url_template": r.download_url_template,
                    "release_url": r.release_url,
                    "prerelease": r.prerelease,
                    "published_at": r.published_at,
                    "assets": list(r.assets),
                }

            data = {
                "refreshed_at": snapshot.refreshed_at,
                "releases_by_source": {
                    source: [_release_to_dict(r) for r in releases]
                    for source, releases in snapshot.releases_by_source.items()
                },
            }
            path = self._catalog_snapshot_path()
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass  # non-fatal

    def load_catalog_snapshot(self) -> FirmwareCatalogSnapshot | None:
        """Load a previously saved catalog snapshot from disk, or return None."""
        self.last_snapshot_load_error = None
        path = self._catalog_snapshot_path()
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))

            def _dict_to_release(d: dict) -> FirmwareRelease:
                return FirmwareRelease(
                    source=str(d.get("source", "")),
                    family=str(d.get("family", "")),
                    key=str(d.get("key", "")),
                    name=str(d.get("name", "")),
                    download_url_template=str(d.get("download_url_template", "")),
                    release_url=d.get("release_url"),
                    prerelease=bool(d.get("prerelease", False)),
                    published_at=str(d.get("published_at", "")),
                    assets=tuple(
                        (str(pair[0]), str(pair[1]))
                        for pair in d.get("assets", [])
                        if isinstance(pair, (list, tuple)) and len(pair) == 2
                    ),
                )

            releases_by_source: dict[str, tuple[FirmwareRelease, ...]] = {}
            for source, releases_raw in raw.get("releases_by_source", {}).items():
                releases_by_source[str(source)] = tuple(
                    _dict_to_release(r) for r in releases_raw if isinstance(r, dict)
                )

            return FirmwareCatalogSnapshot(
                refreshed_at=str(raw.get("refreshed_at", "(cached)")),
                releases_by_source=releases_by_source,
                layouts_by_source={s: () for s in releases_by_source},
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            self.last_snapshot_load_error = str(exc) or type(exc).__name__
            self._quarantine_corrupt_snapshot(path)
            return None

    def _get_bluejay_releases(self) -> list[FirmwareRelease]:
        payload = self._fetch_json(BLUEJAY_RELEASES_URL)
        if not isinstance(payload, list):
            raise ValueError("GitHub releases payload was not a list")

        releases: list[FirmwareRelease] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            tag_name = str(item.get("tag_name", ""))
            if not tag_name or tag_name in BLUEJAY_BLACKLIST:
                continue
            assets = item.get("assets", [])
            if not isinstance(assets, list) or len(assets) == 0:
                continue
            name = str(item.get("name") or tag_name.removeprefix("v"))
            releases.append(
                FirmwareRelease(
                    source="Bluejay",
                    family="Bluejay",
                    key=tag_name,
                    name=name,
                    download_url_template=f"https://github.com/bird-sanctuary/bluejay/releases/download/{tag_name}/",
                    release_url=f"https://github.com/bird-sanctuary/bluejay/releases/tag/{tag_name}/",
                    prerelease=bool(item.get("prerelease", False)),
                    published_at=str(item.get("published_at", "")),
                    assets=tuple(
                        (
                            str(asset.get("name", "")),
                            str(asset.get("browser_download_url", "")),
                        )
                        for asset in assets
                        if isinstance(asset, dict) and asset.get("name") and asset.get("browser_download_url")
                    ),
                )
            )
        return releases

    def _get_blheli_s_releases(self) -> list[FirmwareRelease]:
        return [
            FirmwareRelease(
                source="BLHeli_S",
                family="BLHeli_S",
                key=entry["key"],
                name=entry["name"],
                download_url_template=entry["url"],
                release_url=None,
                prerelease="beta" in entry["name"].lower(),
                published_at="",
            )
            for entry in BLHELI_S_RELEASES
        ]
