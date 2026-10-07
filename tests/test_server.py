"""Exercise the real local HTTP server without touching a user's files."""

from __future__ import annotations

import collections
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

import server


class LocalServerTests(unittest.TestCase):
    def setUp(self):
        # Keep every demo, journal and renamed file in one disposable directory.
        self.temp = tempfile.TemporaryDirectory(prefix=".caos-http-test-", dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.data_dir = self.base / "state"
        self.demo_parent = self.base / "demo"
        self.httpd = None
        self.thread = None
        self.start_server()
        self.addCleanup(self.stop_server)

    def start_server(self):
        self.httpd = server.make_server(
            host="127.0.0.1",
            port=0,
            data_dir=self.data_dir,
            demo_parent=self.demo_parent,
        )
        self.port = self.httpd.server_address[1]
        self.authority = f"127.0.0.1:{self.port}"
        self.token = self.httpd.caos_token
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop_server(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.thread.join(timeout=5)
            self.assertFalse(self.thread.is_alive(), "HTTP server did not stop")
            self.httpd = None

    def request(self, method, target, data=None, headers=None, authenticated=True, raw=None):
        request_headers = {}
        if authenticated:
            request_headers["X-Caos-Token"] = self.token
        if data is not None or raw is not None:
            request_headers["Content-Type"] = "application/json"
        if headers:
            request_headers.update(headers)
        body = raw if raw is not None else (json.dumps(data) if data is not None else None)
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, target, body=body, headers=request_headers)
            response = connection.getresponse()
            payload = response.read()
            content_type = response.getheader("Content-Type", "")
            decoded = json.loads(payload) if "application/json" in content_type else payload.decode("utf-8")
            return response.status, decoded, content_type
        finally:
            connection.close()

    def api(self, method, target, data=None, expected=200):
        status, result, _ = self.request(method, target, data=data)
        self.assertEqual(status, expected, result)
        self.assertIsInstance(result, dict)
        return result

    def assert_error(self, status, response, expected=None):
        if expected is not None:
            self.assertEqual(status, expected, response)
        else:
            self.assertGreaterEqual(status, 400, response)
            self.assertLess(status, 500, response)
        self.assertIsInstance(response, dict)
        self.assertIsInstance(response.get("error"), str)
        self.assertTrue(response["error"])

    @staticmethod
    def snapshot(root):
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*")
            if path.is_file()
        }

    def make_demo(self):
        response = self.api("POST", "/api/demo", {})
        root = Path(response["path"])
        self.assertTrue(root.is_dir())
        self.assertTrue(root.is_relative_to(self.demo_parent))
        self.assertTrue(self.snapshot(root), "Demo must include real example files")
        return root

    def preview(self, root):
        return self.api("POST", "/api/preview", {
            "root": str(root),
            "options": {"organize": True, "grouping": "type", "rename": "keep", "recursive": True},
        })

    def test_demo_preview_apply_and_persistent_undo_preserve_every_byte(self):
        root = self.make_demo()
        before = self.snapshot(root)
        self.assertEqual(Path(self.api("GET", "/api/config")["demo_root"]), root)
        plan = self.preview(root)
        self.assertEqual(self.snapshot(root), before, "Preview must not change files")
        selected_ids = [item["id"] for item in plan["files"] if item["status"] == "ready"]
        self.assertTrue(selected_ids, "Demo must produce a useful organization preview")
        operation = self.api("POST", "/api/apply", {"plan_id": plan["id"], "selected_ids": selected_ids})
        self.assertEqual(operation["state"], "applied")
        self.assertEqual(operation["count"], len(selected_ids))
        after = self.snapshot(root)
        self.assertNotEqual(after, before, "Apply must actually organize files")
        self.assertEqual(collections.Counter(after.values()), collections.Counter(before.values()))
        history = self.api("GET", "/api/history")["operations"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["id"], operation["id"])

        # Undo must work from its persisted journal after the process has restarted.
        old_token = self.token
        self.stop_server()
        self.start_server()
        self.assertNotEqual(self.token, old_token)
        history = self.api("GET", "/api/history")["operations"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["id"], operation["id"])
        self.assertEqual(history[0]["state"], "applied")
        details = self.api("GET", f"/api/operations/{operation['id']}")
        self.assertEqual(details["id"], operation["id"])
        self.assertEqual(details["state"], "applied")
        self.assertEqual(len(details["entries"]), len(selected_ids))
        self.assertEqual(
            {(entry["source"], entry["destination"]) for entry in details["entries"]},
            {(item["source"], item["destination"]) for item in plan["files"] if item["id"] in selected_ids},
        )
        self.assertTrue(all(entry["state"] == "moved" for entry in details["entries"]))
        result = self.api("POST", "/api/undo", {"operation_id": operation["id"]})
        self.assertEqual(result["state"], "undone")
        self.assertEqual(self.snapshot(root), before, "Undo must restore both paths and file bytes")
        self.assertEqual(self.api("GET", "/api/history")["operations"][0]["state"], "undone")
        self.assertEqual(self.api("GET", f"/api/operations/{operation['id']}")["state"], "undone")

    def test_empty_selection_cannot_silently_apply_all_files(self):
        root = self.make_demo()
        before = self.snapshot(root)
        plan = self.preview(root)
        status, response, _ = self.request("POST", "/api/apply", data={"plan_id": plan["id"], "selected_ids": []})
        self.assert_error(status, response, 400)
        self.assertEqual(self.snapshot(root), before)
        self.assertEqual(self.api("GET", "/api/history")["operations"], [])

    def test_partial_selection_only_moves_selected_files(self):
        root = self.make_demo()
        before = self.snapshot(root)
        plan = self.preview(root)
        ready = [item for item in plan["files"] if item["status"] == "ready"]
        self.assertGreater(len(ready), 1)
        operation = self.api("POST", "/api/apply", {"plan_id": plan["id"], "selected_ids": [ready[0]["id"]]})
        self.assertEqual(operation["count"], 1)
        after = self.snapshot(root)
        self.assertEqual(len(set(before) - set(after)), 1)
        self.assertEqual(len(set(after) - set(before)), 1)
        self.assertEqual(collections.Counter(after.values()), collections.Counter(before.values()))
        self.api("POST", "/api/undo", {"operation_id": operation["id"]})
        self.assertEqual(self.snapshot(root), before)

    def test_rename_modes_can_be_previewed_and_undone_without_reorganization(self):
        for mode, expected_name in (("clean", "la-mia-foto.jpg"), ("sequence", "album-001.jpg")):
            with self.subTest(mode=mode):
                root = self.base / mode
                root.mkdir()
                original = root / "La mia FOTO.JPG"
                original.write_bytes(b"A photo placeholder with byte-identical preservation.")
                before = self.snapshot(root)
                plan = self.api("POST", "/api/preview", {
                    "root": str(root),
                    "options": {"organize": False, "rename": mode, "prefix": "album"},
                })
                self.assertEqual(self.snapshot(root), before)
                self.assertEqual(plan["files"][0]["destination"], expected_name)
                operation = self.api("POST", "/api/apply", {
                    "plan_id": plan["id"], "selected_ids": [plan["files"][0]["id"]],
                })
                self.assertFalse(original.exists())
                self.assertEqual(self.snapshot(root), {expected_name: next(iter(before.values()))})
                self.api("POST", "/api/undo", {"operation_id": operation["id"]})
                self.assertEqual(self.snapshot(root), before)

    def test_config_and_static_assets(self):
        config = self.api("GET", "/api/config")
        self.assertEqual(config["csrf"], self.token)
        self.assertTrue(config["version"])
        self.assertTrue(Path(config["home"]).is_absolute())
        self.assertTrue(Path(config["downloads"]).is_absolute())
        self.assertIsNone(config["demo_root"])
        self.assertEqual(self.api("GET", "/api/history")["operations"], [])
        for target, content_type in (("/", "text/html"), ("/styles.css", "text/css"),
                                     ("/app.js", "javascript"), ("/theme.js", "javascript"),
                                     ("/i18n.js", "javascript"), ("/messages.js", "javascript")):
            with self.subTest(target=target):
                status, body, mime = self.request("GET", target)
                self.assertEqual(status, 200, body)
                self.assertIn(content_type, mime)
                self.assertTrue(body.strip())

    def test_second_server_cannot_use_the_same_operation_journal(self):
        with self.assertRaises(ValueError):
            duplicate = server.make_server(
                host="127.0.0.1", port=0, data_dir=self.data_dir, demo_parent=self.demo_parent,
            )
            # Ensure a failed assertion never leaves a duplicate socket open.
            duplicate.server_close()
        self.assertEqual(self.api("GET", "/api/history")["operations"], [])

    def test_post_requires_valid_token(self):
        for headers in ({}, {"X-Caos-Token": "not-the-session-token"}, {"X-Caos-Token": "sessione-erratà"}):
            with self.subTest(headers=headers):
                status, response, _ = self.request("POST", "/api/demo", data={}, authenticated=False, headers=headers)
                self.assert_error(status, response, 403)
        self.assertIsNone(self.httpd.demo_root)

    def test_host_validation_blocks_dns_rebinding(self):
        for host in ("attacker.example", f"attacker.example:{self.port}", f"127.0.0.1.attacker.example:{self.port}", "127.0.0.1:1"):
            with self.subTest(host=host):
                status, response, _ = self.request("GET", "/api/config", headers={"Host": host})
                self.assert_error(status, response, 403)
        for host in (self.authority, f"localhost:{self.port}"):
            with self.subTest(allowed_host=host):
                status, response, _ = self.request("GET", "/api/config", headers={"Host": host})
                self.assertEqual(status, 200, response)

    def test_foreign_origin_is_denied_even_with_token(self):
        for origin in ("https://attacker.example", "null", f"http://127.0.0.1:{self.port + 1}"):
            with self.subTest(origin=origin):
                status, response, _ = self.request("POST", "/api/demo", data={}, headers={"Origin": origin})
                self.assert_error(status, response, 403)
        self.assertIsNone(self.httpd.demo_root)
        status, response, _ = self.request("POST", "/api/demo", data={}, headers={"Sec-Fetch-Site": "cross-site"})
        self.assert_error(status, response, 403)
        status, response, _ = self.request("POST", "/api/demo", data={}, headers={"Origin": f"http://{self.authority}"})
        self.assertEqual(status, 200, response)

    def test_static_paths_never_disclose_source_or_traverse(self):
        targets = ("/server.py", "/../server.py", "/%2e%2e/server.py", "/%2e%2e%2fserver.py", "/tests/test_server.py")
        for target in targets:
            with self.subTest(target=target):
                status, _, _ = self.request("GET", target)
                self.assertIn(status, (400, 403, 404))

    def test_operation_details_reject_invalid_ids_and_path_traversal(self):
        for operation_id in ("..", "../server.py", "%2e%2e", "not-an-operation", "0" * 32, ""):
            with self.subTest(operation_id=operation_id):
                status, response, _ = self.request("GET", f"/api/operations/{operation_id}")
                self.assert_error(status, response, 400)

    def test_malformed_json_and_unknown_api_return_errors(self):
        status, response, _ = self.request("POST", "/api/preview", raw="{broken")
        self.assert_error(status, response, 400)
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                status, response, _ = self.request(method, "/api/does-not-exist", data={} if method == "POST" else None)
                self.assert_error(status, response, 404)

    def test_invalid_payloads_are_rejected_without_mutation(self):
        root = self.make_demo()
        before = self.snapshot(root)
        plan = self.preview(root)
        cases = (
            ("/api/demo", {"raw": "[]"}),
            ("/api/demo", {"data": {}, "headers": {"Content-Type": "text/plain"}}),
            ("/api/preview", {"data": {"root": []}}),
            ("/api/preview", {"data": {"root": str(root), "options": []}}),
            ("/api/apply", {"data": {"plan_id": plan["id"], "selected_ids": "all"}}),
            ("/api/apply", {"data": {"plan_id": plan["id"], "selected_ids": [1]}}),
            ("/api/undo", {"data": {"operation_id": []}}),
        )
        for target, kwargs in cases:
            with self.subTest(target=target, kwargs=kwargs):
                status, response, _ = self.request("POST", target, **kwargs)
                self.assert_error(status, response, 400)
                self.assertEqual(self.snapshot(root), before)
                self.assertEqual(self.api("GET", "/api/history")["operations"], [])


if __name__ == "__main__":
    unittest.main()
