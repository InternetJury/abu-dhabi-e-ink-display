from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_a6_publisher_uses_atomic_remote_frame_rename():
    script = (REPO_ROOT / "deploy" / "a6" / "run-render-publisher.ps1").read_text()

    assert '$remoteTmp = "$RemotePath.tmp"' in script
    assert "& scp -q $currentFrame" in script
    assert "mv '$remoteTmp' '$RemotePath'" in script


def test_waveshare_install_uses_dedicated_dual_controller_adapter():
    script = (REPO_ROOT / "deploy" / "pi" / "install-waveshare-10in85.sh").read_text()

    assert "WAVESHARE_10IN85_SPI_HZ=\"2000000\"" in script
    assert "--driver-module waveshare_10in85_bw" in script
    assert "--disable-partial" not in script
