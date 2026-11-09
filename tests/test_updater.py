"""Testes da atualização automática, sem acesso à internet."""

import hashlib
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import updater  # noqa: E402

PREFIX = updater.DOWNLOAD_URL_PREFIX


def release_payload(tag="v2.0.0", **overrides):
    payload = {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "assets": [
            {"name": updater.EXE_ASSET_NAME, "size": 10,
             "browser_download_url": f"{PREFIX}{tag}/{updater.EXE_ASSET_NAME}"},
            {"name": updater.HASH_ASSET_NAME, "size": 80,
             "browser_download_url": f"{PREFIX}{tag}/{updater.HASH_ASSET_NAME}"},
        ],
    }
    payload.update(overrides)
    return payload


class VersionTests(unittest.TestCase):
    def test_comparison_is_numeric_not_alphabetic(self):
        self.assertTrue(updater.is_newer("v1.10.0", "1.9.0"))

    def test_same_or_older_version_is_not_an_update(self):
        self.assertFalse(updater.is_newer("v1.1.0", "1.1.0"))
        self.assertFalse(updater.is_newer("v1.0.9", "1.1.0"))

    def test_unrecognized_tag_is_not_an_update(self):
        self.assertFalse(updater.is_newer("beta", "1.1.0"))


class ReleaseParsingTests(unittest.TestCase):
    def test_newer_release_is_accepted(self):
        release = updater.parse_release(release_payload(), "1.1.0")
        self.assertEqual(release.version, "2.0.0")
        self.assertEqual(release.size, 10)

    def test_older_release_is_ignored(self):
        self.assertIsNone(updater.parse_release(release_payload("v1.0.0"), "1.1.0"))

    def test_prerelease_is_ignored(self):
        self.assertIsNone(updater.parse_release(release_payload(prerelease=True), "1.1.0"))

    def test_release_without_hash_file_is_ignored(self):
        payload = release_payload()
        payload["assets"] = payload["assets"][:1]
        self.assertIsNone(updater.parse_release(payload, "1.1.0"))

    def test_download_outside_the_repository_is_rejected(self):
        payload = release_payload()
        payload["assets"][0]["browser_download_url"] = "https://exemplo.com/RenomeadorCTE.exe"
        self.assertIsNone(updater.parse_release(payload, "1.1.0"))

    def test_network_failure_means_no_update(self):
        with mock.patch.object(updater, "_open_url", side_effect=OSError("sem internet")) as opened, \
                mock.patch.object(updater, "RETRY_DELAY_SECONDS", 0):
            self.assertIsNone(updater.find_update("1.1.0"))
        self.assertEqual(opened.call_count, updater.CHECK_ATTEMPTS)

    def test_momentary_failure_is_retried(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(release_payload()).encode()
        with mock.patch.object(updater, "_open_url", side_effect=[OSError("falha"), response]), \
                mock.patch.object(updater, "RETRY_DELAY_SECONDS", 0):
            self.assertEqual(updater.find_update("1.1.0").version, "2.0.0")

    def test_missing_release_is_not_retried(self):
        error = urllib.error.HTTPError("url", 404, "Not Found", None, None)
        with mock.patch.object(updater, "_open_url", side_effect=error) as opened:
            self.assertIsNone(updater.find_update("1.1.0"))
        self.assertEqual(opened.call_count, 1)

    def test_closing_the_program_stops_retries(self):
        stop = threading.Event()
        stop.set()
        with mock.patch.object(updater, "_open_url", side_effect=OSError("falha")) as opened:
            self.assertIsNone(updater.find_update("1.1.0", stop=stop))
        self.assertEqual(opened.call_count, 1)


class HashParsingTests(unittest.TestCase):
    def test_accepts_hash_followed_by_filename(self):
        value = "A" * 64
        self.assertEqual(updater.parse_hash(f"{value}  RenomeadorCTE.exe\n"), "a" * 64)

    def test_rejects_invalid_content(self):
        with self.assertRaises(updater.UpdateError):
            updater.parse_hash("Not Found")


class DownloadTests(unittest.TestCase):
    CONTENT = b"novo executavel" * 40_000

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.target = self.dir / "app.exe.new"
        self.hash_text = hashlib.sha256(self.CONTENT).hexdigest()
        test_case = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = test_case.hash_text.encode() if self.path == "/hash" else test_case.CONTENT
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.release = updater.ReleaseInfo("2.0.0", f"{base}/exe", f"{base}/hash", len(self.CONTENT))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self._tmp.cleanup()

    def test_successful_download_reports_progress(self):
        events = []
        self.assertTrue(updater.download_update(self.release, self.target, lambda d, t: events.append((d, t))))
        self.assertEqual(self.target.read_bytes(), self.CONTENT)
        self.assertEqual(events[-1], (len(self.CONTENT), len(self.CONTENT)))

    def test_wrong_hash_removes_the_file(self):
        self.hash_text = "0" * 64
        with self.assertRaises(updater.UpdateError):
            updater.download_update(self.release, self.target)
        self.assertFalse(self.target.exists())

    def test_cancel_removes_the_file(self):
        cancel = threading.Event()
        cancel.set()
        self.assertFalse(updater.download_update(self.release, self.target, cancel=cancel))
        self.assertFalse(self.target.exists())

    def test_unreachable_server_raises_friendly_error(self):
        dead = updater.ReleaseInfo("2.0.0", "http://127.0.0.1:9/exe", "http://127.0.0.1:9/hash", 1)
        with mock.patch.object(updater, "RETRY_DELAY_SECONDS", 0), \
                self.assertRaises(updater.UpdateError):
            updater.download_update(dead, self.target)
        self.assertFalse(self.target.exists())

    def test_dropped_connection_is_retried(self):
        real_open = updater._open_url
        calls = []

        def drops_first_download(url, timeout):
            calls.append(url)
            if url == self.release.exe_url and calls.count(url) == 1:
                raise TimeoutError("timed out")
            return real_open(url, timeout)

        with mock.patch.object(updater, "_open_url", drops_first_download), \
                mock.patch.object(updater, "RETRY_DELAY_SECONDS", 0):
            self.assertTrue(updater.download_update(self.release, self.target))
        self.assertEqual(self.target.read_bytes(), self.CONTENT)

    def test_wrong_hash_is_not_retried(self):
        self.hash_text = "0" * 64
        with mock.patch.object(updater, "_open_url", wraps=updater._open_url) as opened, \
                self.assertRaises(updater.UpdateError):
            updater.download_update(self.release, self.target)
        self.assertEqual(opened.call_count, 2)  # só o hash e o executável, uma vez cada


class InstallTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.exe = self.dir / "app.exe"
        self.exe.write_bytes(b"antigo")
        self.new = updater.download_path(self.exe)
        self.new.write_bytes(b"novo")
        self.previous = updater.previous_version_path(self.exe)

    def tearDown(self):
        self._tmp.cleanup()

    def test_swaps_files_and_launches_the_new_version(self):
        launched = []
        updater.install_and_restart(self.new, self.exe, launched.append)
        self.assertEqual(self.exe.read_bytes(), b"novo")
        self.assertEqual(self.previous.read_bytes(), b"antigo")
        self.assertEqual(launched, [self.exe])

    def test_launch_failure_restores_the_working_version(self):
        def broken_launcher(_path):
            raise OSError("bloqueado pelo antivírus")

        with self.assertRaises(updater.UpdateError):
            updater.install_and_restart(self.new, self.exe, broken_launcher)
        self.assertEqual(self.exe.read_bytes(), b"antigo")
        self.assertFalse(self.previous.exists())
        self.assertFalse(self.new.exists())

    def test_new_version_removes_the_previous_one(self):
        updater.install_and_restart(self.new, self.exe, lambda _path: None)
        self.assertTrue(updater.remove_previous_version(self.exe, attempts=1, delay=0))
        self.assertFalse(self.previous.exists())
        self.assertEqual(self.exe.read_bytes(), b"novo")

    def test_cleanup_waits_while_the_old_file_is_locked(self):
        self.previous.write_bytes(b"antigo")
        real_unlink = Path.unlink
        calls = []

        def flaky_unlink(path, missing_ok=False):
            if path == self.previous and not calls:
                calls.append(path)
                raise PermissionError("em uso")
            real_unlink(path, missing_ok=missing_ok)

        with mock.patch.object(Path, "unlink", flaky_unlink):
            self.assertTrue(updater.remove_previous_version(self.exe, attempts=3, delay=0))
        self.assertFalse(self.previous.exists())


if __name__ == "__main__":
    unittest.main()
