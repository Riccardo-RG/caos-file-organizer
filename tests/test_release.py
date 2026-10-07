"""Exercise startup, shutdown and distribution using disposable state only."""

from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import errno
import http.client
import io
import json
from pathlib import Path
import queue
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import zipfile

import server


APP_DIR = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".caos-release-test-", dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.data_dir = self.base / "state"

    def make_server(self, **kwargs):
        return server.make_server(data_dir=self.data_dir, demo_parent=self.base / "demos", **kwargs)

    @contextmanager
    def running_cli(self, port=0):
        process = subprocess.Popen(
            [sys.executable, "-u", str(APP_DIR / "server.py"), "--no-browser",
             "--port", str(port), "--data-dir", str(self.data_dir)],
            cwd=APP_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        lines = queue.Queue()

        def collect_output():
            for line in process.stdout:
                lines.put(line)
            lines.put(None)

        reader = threading.Thread(target=collect_output, daemon=True)
        reader.start()
        output = []
        try:
            while True:
                line = lines.get(timeout=10)
                self.assertIsNotNone(line, "Startup failed: " + "".join(output))
                output.append(line)
                match = re.search(r"http://127\.0\.0\.1:(\d+)", line)
                if match:
                    break
            yield process, int(match.group(1))
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                self.fail("Caos did not shut down within ten seconds")
            reader.join(timeout=2)
            process.stdout.close()

    @staticmethod
    def get_config(port):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", "/api/config")
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_loopback_startup_does_not_depend_on_dns(self):
        with mock.patch.object(socket, "getfqdn", side_effect=AssertionError("Startup must not query DNS")):
            httpd = self.make_server(port=0)
        try:
            self.assertEqual(httpd.server_name, "127.0.0.1")
            self.assertGreater(httpd.server_port, 0)
        finally:
            httpd.server_close()

    def test_bind_failure_releases_history_lock_for_retry(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            with self.assertRaises(OSError):
                self.make_server(port=occupied.getsockname()[1])
            recovered = self.make_server(port=0)
            recovered.server_close()

    def test_cli_occupied_port_falls_back_and_terminates_cleanly(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            occupied_port = occupied.getsockname()[1]
            with self.running_cli(occupied_port) as (process, port):
                self.assertNotEqual(port, occupied_port)
                status, config = self.get_config(port)
                self.assertEqual(status, 200)
                self.assertTrue(config["csrf"])
                process.terminate()
                self.assertEqual(process.wait(timeout=5), 0)
        # The graceful exit must release the journal for the next launch.
        restarted = self.make_server(port=0)
        restarted.server_close()

    def test_cli_ctrl_c_exits_successfully_and_releases_journal(self):
        with self.running_cli() as (process, port):
            self.assertEqual(self.get_config(port)[0], 200)
            process.send_signal(signal.SIGINT)
            self.assertEqual(process.wait(timeout=5), 0)
        restarted = self.make_server(port=0)
        restarted.server_close()

    def test_second_cli_launch_reuses_the_live_instance(self):
        with self.running_cli() as (first, port):
            status, config = self.get_config(port)
            self.assertEqual(status, 200)
            second = subprocess.run(
                [sys.executable, str(APP_DIR / "server.py"), "--no-browser",
                 "--port", "0", "--data-dir", str(self.data_dir)],
                cwd=APP_DIR, capture_output=True, text=True, timeout=5,
            )
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn(f"http://127.0.0.1:{port}", second.stdout)
            self.assertIsNone(first.poll())
            self.assertEqual(self.get_config(port)[1]["csrf"], config["csrf"])

    def test_second_launch_opens_existing_browser_unless_suppressed(self):
        with self.running_cli() as (_, port):
            for no_browser in (False, True):
                with self.subTest(no_browser=no_browser):
                    arguments = ["--data-dir", str(self.data_dir), "--port", "0"]
                    if no_browser:
                        arguments.append("--no-browser")
                    with mock.patch.object(server.webbrowser, "open") as open_browser, redirect_stdout(io.StringIO()):
                        self.assertEqual(server.main(arguments), 0)
                    if no_browser:
                        open_browser.assert_not_called()
                    else:
                        open_browser.assert_called_once_with(f"http://127.0.0.1:{port}")

    def test_existing_instance_identity_must_match_before_opening_browser(self):
        with self.running_cli() as (_, port):
            instance = {"port": port, "instance_id": "wrong-instance"}
            self.assertIsNone(server.existing_instance_url(instance))
            with mock.patch.object(server, "make_server", side_effect=server.AlreadyRunning(instance)), \
                    mock.patch.object(server.webbrowser, "open") as open_browser, redirect_stderr(io.StringIO()):
                self.assertEqual(server.main(["--data-dir", str(self.data_dir)]), 1)
                open_browser.assert_not_called()

    def test_stale_or_invalid_instance_record_does_not_redirect(self):
        invalid = (None, [], {}, {"port": True, "instance_id": "id"},
                   {"port": "8765", "instance_id": "id"}, {"port": 65536, "instance_id": "id"},
                   {"port": 8765, "instance_id": None}, {"port": 8765, "instance_id": ""},
                   {"url": "https://unrelated.invalid"})
        for instance in invalid:
            with self.subTest(instance=instance), mock.patch.object(server, "HTTPConnection") as request:
                self.assertIsNone(server.existing_instance_url(instance))
                request.assert_not_called()
        with mock.patch.object(server, "HTTPConnection") as connection:
            connection.return_value.request.side_effect = ConnectionRefusedError
            self.assertIsNone(server.existing_instance_url({"port": 8765, "instance_id": "stale"}))

    def test_existing_instance_does_not_follow_redirects(self):
        with mock.patch.object(server, "HTTPConnection") as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 302
            response.read.return_value = b'{"instance_id": "expected"}'
            response.getheader.return_value = "https://unrelated.invalid/config"
            self.assertIsNone(server.existing_instance_url({"port": 8765, "instance_id": "expected"}))
            connection.assert_called_once_with("127.0.0.1", 8765, timeout=2)
            connection.return_value.request.assert_called_once_with("GET", "/api/config")

    def test_cli_startup_permission_failure_is_readable(self):
        output = io.StringIO()
        with mock.patch.object(server, "make_server", side_effect=PermissionError(errno.EACCES, "Accesso negato")), \
                mock.patch.object(server.webbrowser, "open") as open_browser, redirect_stderr(output):
            self.assertEqual(server.main(["--data-dir", str(self.data_dir)]), 1)
            open_browser.assert_not_called()
        self.assertTrue(output.getvalue().strip())
        self.assertNotIn("Traceback", output.getvalue())

    def test_new_http_connections_have_bounded_idle_wait(self):
        httpd = self.make_server(port=0)
        observed = queue.Queue()
        original_setup = server.CaosHandler.setup

        def setup(handler):
            original_setup(handler)
            observed.put(handler.connection.gettimeout())

        with mock.patch.object(server.CaosHandler, "setup", setup):
            worker = threading.Thread(target=httpd.serve_forever, daemon=True)
            worker.start()
            connection = socket.create_connection(httpd.server_address, timeout=5)
            try:
                timeout = observed.get(timeout=5)
                self.assertIsNotNone(timeout, "An idle browser connection must not block shutdown forever")
                self.assertGreater(timeout, 0)
                self.assertLessEqual(timeout, 30)
            finally:
                connection.close()
                httpd.shutdown()
                httpd.server_close()
                worker.join(timeout=5)

    def test_shutdown_waits_for_an_inflight_filesystem_operation(self):
        httpd = self.make_server(port=0)
        entered = threading.Event()
        release = threading.Event()
        closed = threading.Event()
        responses = queue.Queue()

        def slow_preview(*_args):
            entered.set()
            if not release.wait(timeout=10):
                raise RuntimeError("The test did not release its operation")
            return {"finished": True}

        def request_preview():
            client = http.client.HTTPConnection(*httpd.server_address, timeout=10)
            try:
                client.request("POST", "/api/preview", json.dumps({"root": str(self.base)}),
                               {"Content-Type": "application/json", "X-Caos-Token": httpd.caos_token})
                response = client.getresponse()
                responses.put((response.status, json.loads(response.read())))
            except Exception as exc:
                responses.put(exc)
            finally:
                client.close()

        def stop_server():
            httpd.shutdown()
            httpd.server_close()
            closed.set()

        with mock.patch.object(httpd.organizer, "preview", slow_preview):
            worker = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
            client = threading.Thread(target=request_preview, daemon=True)
            worker.start()
            client.start()
            closer = None
            try:
                self.assertTrue(entered.wait(timeout=5))
                closer = threading.Thread(target=stop_server, daemon=True)
                closer.start()
                self.assertFalse(closed.wait(timeout=0.15), "Shutdown must wait until filesystem work finishes")
                release.set()
                self.assertTrue(closed.wait(timeout=5))
                self.assertEqual(responses.get(timeout=5), (200, {"finished": True}))
            finally:
                release.set()
                if closer is None:
                    stop_server()
                else:
                    closer.join(timeout=5)
                worker.join(timeout=5)
                client.join(timeout=5)

    def test_release_archive_is_self_contained_and_launcher_is_executable(self):
        release = '.'.join(server.VERSION.split('.')[:2])
        archive_path = APP_DIR / "dist" / f"Caos-{release}.zip"
        if not archive_path.exists():
            self.skipTest("Distribution archive is absent in a source-only checkout")
        required = {"server.py", "organizer.py", "Avvia Caos.command", "README.md", "build_release.py",
                    "tests/test_release.py", "tests/test_server.py", "tests/test_organizer.py",
                    "web/index.html", "web/app.js", "web/styles.css", "web/favicon.svg", "web/theme.js",
                    "web/i18n.js", "web/messages.js",
                    "VERIFICATION.md", ".gitignore", ".github/workflows/ci.yml",
                    "docs/screenshots/light.jpg", "docs/screenshots/dark.jpg"}
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            self.assertTrue({"Caos/" + name for name in required} <= names)
            self.assertEqual(archive.testzip(), None)
            self.assertTrue(archive.getinfo("Caos/Avvia Caos.command").external_attr >> 16 & 0o111)
            for name in required:
                self.assertEqual(archive.read("Caos/" + name), (APP_DIR / name).read_bytes(),
                                 f"Distribution contains a stale copy of {name}")
            for name in names:
                parts = Path(name).parts
                self.assertNotIn(".caos-data", parts)
                self.assertNotIn("esempi", parts)
                self.assertNotIn("__pycache__", parts)


if __name__ == "__main__":
    unittest.main()
