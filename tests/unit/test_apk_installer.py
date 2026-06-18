import subprocess as sp
from unittest.mock import MagicMock, patch

from agent.infra.adb_client import ADBResult
from agent.reproduce import apk_installer


def test_install_delegates():
    c = MagicMock()
    c.install_apk.return_value = ADBResult(True, b"Success", b"", 0, 5)
    r = apk_installer.install(c, "/tmp/app.apk")
    c.install_apk.assert_called_once()
    assert r.success


def test_install_with_device_id():
    c = MagicMock()
    c.install_apk.return_value = ADBResult(True, b"Success", b"", 0, 5)
    apk_installer.install(c, "/tmp/app.apk", device_id="emulator-5554")
    c.install_apk.assert_called_once_with(
        "/tmp/app.apk", device_id="emulator-5554"
    )


def test_launch_calls_subprocess():
    fake_proc = sp.CompletedProcess(
        args=[], returncode=0, stdout=b"ok", stderr=b""
    )
    with patch("subprocess.run", return_value=fake_proc) as m:
        r = apk_installer.launch(MagicMock(), "com.example", ".MainActivity")
    assert r.success
    called_args = m.call_args[0][0]
    assert "am" in called_args
    assert "start" in called_args
    assert "com.example/.MainActivity" in called_args


def test_launch_with_device_id():
    fake_proc = sp.CompletedProcess(
        args=[], returncode=0, stdout=b"ok", stderr=b""
    )
    with patch("subprocess.run", return_value=fake_proc) as m:
        apk_installer.launch(
            MagicMock(), "com.example", ".MainActivity", device_id="emulator-5554"
        )
    called_args = m.call_args[0][0]
    assert "-s" in called_args
    assert "emulator-5554" in called_args


def test_uninstall_calls_subprocess():
    fake_proc = sp.CompletedProcess(
        args=[], returncode=0, stdout=b"ok", stderr=b""
    )
    with patch("subprocess.run", return_value=fake_proc) as m:
        apk_installer.uninstall(MagicMock(), "com.example")
    called_args = m.call_args[0][0]
    assert "uninstall" in called_args
    assert "com.example" in called_args


def test_get_installed_version_parses():
    fake_proc = sp.CompletedProcess(
        args=[],
        returncode=0,
        stdout="versionName=1.2.3\nother=line\n",
        stderr=b"",
    )
    with patch("subprocess.run", return_value=fake_proc):
        v = apk_installer.get_installed_version(MagicMock(), "com.example")
    assert v == "1.2.3"


def test_get_installed_version_not_installed():
    fake_proc = sp.CompletedProcess(
        args=[], returncode=0, stdout="no package", stderr=b""
    )
    with patch("subprocess.run", return_value=fake_proc):
        v = apk_installer.get_installed_version(MagicMock(), "com.example")
    assert v is None


def test_get_installed_version_timeout_returns_none():
    with patch(
        "subprocess.run", side_effect=sp.TimeoutExpired(cmd="adb", timeout=10)
    ):
        v = apk_installer.get_installed_version(MagicMock(), "com.example")
    assert v is None
