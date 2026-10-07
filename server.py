#!/usr/bin/env python3
"""Caos: a private, loopback-only interface for the file organizer."""
from __future__ import annotations

import argparse
import base64
import fcntl
import json
import os
from pathlib import Path
import secrets
import signal
import socket
from socketserver import TCPServer
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.client import HTTPConnection, HTTPException
from urllib.parse import parse_qs, urlsplit
import webbrowser
import zipfile

from organizer import Organizer, OrganizerError

APP_DIR = Path(__file__).resolve().parent
VERSION = "1.2.0"
MAX_BODY = 4 * 1024 * 1024


class AlreadyRunning(ValueError):
    def __init__(self, instance):
        super().__init__("Caos è già aperto con questa cronologia. Usa la finestra esistente oppure chiudila prima di riavviare.")
        self.instance = instance


class CaosServer(ThreadingHTTPServer):
    daemon_threads = False  # Finish filesystem operations before shutting down.
    block_on_close = True

    def server_bind(self):
        # HTTPServer normally performs a reverse-DNS lookup here. A loopback
        # application already knows its address; a slow resolver must not delay
        # startup or require any external network access.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    def __init__(self, address, data_dir: Path, demo_parent: Path):
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._lock_file = (data_dir / "server.lock").open("a+")
        try:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            try:
                self._lock_file.seek(0)
                instance = json.load(self._lock_file)
            except (OSError, ValueError):
                instance = None
            self._lock_file.close()
            raise AlreadyRunning(instance) from None
        try:
            self.instance_id = secrets.token_urlsafe(24)
            self.caos_token = secrets.token_urlsafe(32)
            self.organizer = Organizer(data_dir)
            self.operation_lock = threading.RLock()
            self.demo_parent = demo_parent
            self.demo_root = None
            super().__init__(address, CaosHandler)
            self._lock_file.seek(0)
            self._lock_file.truncate()
            json.dump({"port": self.server_port, "instance_id": self.instance_id}, self._lock_file)
            self._lock_file.flush()
            os.fsync(self._lock_file.fileno())
        except Exception:
            self._lock_file.close()
            raise

    def server_close(self):
        super().server_close()
        if hasattr(self, "_lock_file") and not self._lock_file.closed:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            self._lock_file.close()


class CaosHandler(BaseHTTPRequestHandler):
    server_version = "Caos/1.2"
    sys_version = ""

    def setup(self):
        super().setup()
        # A browser may preconnect without sending headers. Bound the idle wait
        # while still waiting for real filesystem operations during shutdown.
        self.connection.settimeout(5)

    def log_message(self, fmt, *args):
        # Do not record personal paths or filenames in HTTP logs.
        pass

    def _send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, status: int, data):
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _trusted(self, mutate=False):
        port = self.server.server_port
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = self.headers.get("Host", "")
        if host not in allowed_hosts:
            self._json(403, {"error": "Indirizzo non autorizzato. Apri l'app dal suo indirizzo locale."})
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != f"http://{host}":
            self._json(403, {"error": "Richiesta da un'altra pagina non consentita."})
            return False
        if self.headers.get("Sec-Fetch-Site") in {"cross-site"}:
            self._json(403, {"error": "Richiesta da un'altra pagina non consentita."})
            return False
        provided_token = self.headers.get("X-Caos-Token", "")
        if mutate and (not provided_token.isascii() or not secrets.compare_digest(provided_token, self.server.caos_token)):
            self._json(403, {"error": "Sessione non valida. Ricarica la pagina e riprova."})
            return False
        return True

    def do_GET(self):
        if not self._trusted():
            return
        path = urlsplit(self.path).path
        if path == "/api/config":
            self._json(200, {"csrf": self.server.caos_token, "home": str(Path.home()),
                             "downloads": str(Path.home() / "Downloads"),
                             "documents": str(Path.home() / "Documents"), "desktop": str(Path.home() / "Desktop"),
                             "version": VERSION, "instance_id": self.server.instance_id,
                             "demo_root": self.server.demo_root})
        elif path == "/api/folders":
            try:
                query = parse_qs(urlsplit(self.path).query)
                self._json(200, list_folders(self.server.organizer, query.get("path", [str(Path.home())])[0]))
            except (ValueError, OrganizerError) as exc:
                self._json(400, {"error": str(exc)})
            except PermissionError:
                self._json(403, {"error": "Non hai accesso a questa cartella. Scegline un'altra o verifica i permessi di macOS."})
            except OSError:
                self._json(400, {"error": "La cartella non è disponibile. Scegline un'altra."})
        elif path == "/api/history":
            with self.server.operation_lock:
                self._json(200, {"operations": self.server.organizer.history()})
        elif path.startswith("/api/operations/"):
            try:
                with self.server.operation_lock:
                    self._json(200, self.server.organizer.details(path.removeprefix("/api/operations/")))
            except (ValueError, OrganizerError) as exc:
                self._json(400, {"error": str(exc)})
        else:
            assets = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/favicon.svg": ("favicon.svg", "image/svg+xml"),
                      "/theme.js": ("theme.js", "text/javascript; charset=utf-8"),
                      "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"),
                      "/messages.js": ("messages.js", "text/javascript; charset=utf-8")}
            if path not in assets:
                self._json(404, {"error": "Pagina non trovata."})
                return
            filename, mime = assets[path]
            try:
                self._send(200, (APP_DIR / "web" / filename).read_bytes(), mime)
            except OSError:
                self._json(404, {"error": "Risorsa non disponibile."})

    def do_POST(self):
        if not self._trusted(mutate=True):
            return
        try:
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Formato della richiesta non supportato.")
            if self.headers.get_content_type() != "application/json":
                raise ValueError("La richiesta deve contenere dati JSON.")
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                raise ValueError("Dimensione della richiesta non valida.")
            self.connection.settimeout(20)
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Formato della richiesta non valido.")
            path = urlsplit(self.path).path
            with self.server.operation_lock:
                if path == "/api/demo":
                    demo = create_demo(self.server.demo_parent)
                    self.server.demo_root = str(demo)
                    result = {"path": str(demo)}
                elif path == "/api/preview":
                    root = payload.get("root")
                    options = payload.get("options", {})
                    if not isinstance(root, str) or not root.strip():
                        raise ValueError("Scegli prima una cartella.")
                    if not isinstance(options, dict):
                        raise ValueError("Opzioni non valide.")
                    result = self.server.organizer.preview(root, options)
                elif path == "/api/apply":
                    plan_id = payload.get("plan_id")
                    ids = payload.get("selected_ids")
                    if not isinstance(plan_id, str):
                        raise ValueError("Genera prima un'anteprima.")
                    if ids is not None and (not isinstance(ids, list) or not all(isinstance(i, str) for i in ids)):
                        raise ValueError("Selezione dei file non valida.")
                    result = self.server.organizer.apply(plan_id, ids)
                elif path == "/api/undo":
                    operation_id = payload.get("operation_id")
                    if not isinstance(operation_id, str):
                        raise ValueError("Operazione non valida.")
                    result = self.server.organizer.undo(operation_id)
                else:
                    self._json(404, {"error": "Operazione non trovata."})
                    return
            self._json(200, result)
        except (ValueError, OrganizerError, UnicodeError) as exc:
            self._json(400, {"error": str(exc) or "Richiesta non valida."})
        except PermissionError:
            self._json(403, {"error": "Accesso alla cartella negato. Controlla i permessi del Terminale nelle impostazioni di macOS, oppure scegli un'altra cartella."})
        except FileNotFoundError:
            self._json(400, {"error": "La cartella o un file non esiste più. Genera una nuova anteprima."})
        except (TimeoutError, socket.timeout):
            self._json(408, {"error": "L'operazione ha impiegato troppo tempo. Riprova."})
        except OSError as exc:
            self._json(400, {"error": f"Impossibile completare l'operazione: {exc.strerror or str(exc)}"})
        except Exception:
            self._json(500, {"error": "Errore inatteso. Controlla la cronologia prima di riprovare: eventuali spostamenti restano registrati."})


def list_folders(organizer: Organizer, raw_path: str):
    """Read-only folder navigation, using the same root checks as previews."""
    if not isinstance(raw_path, str) or not raw_path.strip() or "\x00" in raw_path:
        raise ValueError("Inserisci il percorso completo di una cartella.")
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        raise ValueError("Inserisci il percorso completo di una cartella.")
    path = candidate.resolve(strict=True)
    if not path.is_dir():
        raise ValueError("Il percorso non indica una cartella.")
    can_select, reason = True, None
    try:
        _, fd = organizer._root(str(path))
        os.close(fd)
    except OrganizerError as exc:
        can_select, reason = False, str(exc)
    folders = []
    # Navigation through filesystem roots is allowed; protected contents are not.
    navigable = path in (Path("/"), Path("/private"), Path("/private/var"))
    if can_select or navigable:
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.name.startswith(".") or entry.is_symlink():
                    continue
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    child = path / entry.name
                    try:
                        _, fd = organizer._root(str(child))
                        os.close(fd)
                    except OrganizerError:
                        if child not in (Path("/private"), Path("/private/var")):
                            continue
                    folders.append({"name": entry.name, "path": str(child)})
                except OSError:
                    continue
    folders.sort(key=lambda item: (item["name"].casefold(), item["name"]))
    return {"path": str(path), "parent": str(path.parent) if path.parent != path else None,
            "folders": folders, "can_select": can_select, "reason": reason}


def existing_instance_url(instance):
    """Never trust a stale lock file or open an arbitrary URL from it."""
    if not isinstance(instance, dict):
        return None
    port, identity = instance.get("port"), instance.get("instance_id")
    if type(port) is not int or not 1 <= port <= 65535 or not isinstance(identity, str) or not identity:
        return None
    url = f"http://127.0.0.1:{port}"
    connection = None
    try:
        connection = HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request("GET", "/api/config")
        response = connection.getresponse()
        if response.status != 200:
            return None
        current = json.loads(response.read(16384))
        if secrets.compare_digest(str(current.get("instance_id", "")).encode(), identity.encode()):
            return url
    except (OSError, ValueError, AttributeError, HTTPException):
        pass
    finally:
        if connection is not None:
            connection.close()
    return None


def create_demo(parent: Path) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="Prova-", dir=str(parent)))
    (root / "appunti della riunione.txt").write_text("File di esempio di Caos.\nOgni file, al suo posto.\n", encoding="utf-8")
    (root / "Lista idee.csv").write_text("idea,stato\nRiordinare i file,da fare\nProvare Caos,in corso\n", encoding="utf-8")
    (root / "LEGGIMI.md").write_text("# Una cartella tutta da riordinare\n\nQuesti sono soltanto file di esempio.\n", encoding="utf-8")
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="500"><rect width="800" height="500" fill="#e5eee9"/><circle cx="610" cy="140" r="60" fill="#efaa74"/><path d="M0 500L250 120L560 500M310 500L560 210L800 500" fill="#38675b"/></svg>'
    (root / "Vacanze in montagna.svg").write_text(svg, encoding="utf-8")
    (root / "Screenshot 2026-10-07.png").write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="))
    with zipfile.ZipFile(root / "Documenti vecchi.zip", "w") as archive:
        archive.writestr("esempio.txt", "Un piccolo archivio dimostrativo.")
    (root / "il mio script.py").write_text('print("Ciao, ordine!")\n', encoding="utf-8")
    (root / "file da capire.xyz").write_text("Un file di tipo sconosciuto: finirà in Altro.\n", encoding="utf-8")
    nested = root / "Una sottocartella"
    nested.mkdir()
    (nested / "Altri appunti.txt").write_text("Visibile attivando Includi sottocartelle.\n", encoding="utf-8")
    # Stable dates make the month grouping easy to understand in the demo.
    for index, item in enumerate(sorted(root.rglob("*"))):
        if item.is_file():
            timestamp = 1754006400 + (index % 3) * 32 * 86400
            os.utime(item, (timestamp, timestamp))
    return root


def make_server(host="127.0.0.1", port=0, data_dir=None, demo_parent=None):
    if host != "127.0.0.1":
        raise ValueError("Caos può ascoltare soltanto su 127.0.0.1.")
    return CaosServer((host, port), Path(data_dir or APP_DIR / ".caos-data"), Path(demo_parent or APP_DIR / "esempi"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Caos — Ogni file, al suo posto.")
    parser.add_argument("--port", type=int, default=8765, help="Porta locale (predefinita: 8765, 0 = libera)")
    parser.add_argument("--no-browser", action="store_true", help="Non aprire automaticamente il browser")
    parser.add_argument("--data-dir", type=Path, default=APP_DIR / ".caos-data", help="Cartella della cronologia")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("La porta deve essere compresa tra 0 e 65535.")
    try:
        server = make_server(port=args.port, data_dir=args.data_dir)
    except AlreadyRunning as exc:
        url = existing_instance_url(exc.instance)
        if url:
            print(f"\n  Caos è già aperto: {url}\n", flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            return 0
        print(f"\n  {exc}\n", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"\n  {exc}\n", file=sys.stderr)
        return 1
    except OSError as exc:
        if exc.errno not in (48, 98, 10048) or args.port == 0:
            print(f"\n  Impossibile avviare Caos: {exc.strerror or str(exc)}.\n  Verifica che la cartella del programma e della cronologia siano accessibili.\n", file=sys.stderr)
            return 1
        try:
            server = make_server(port=0, data_dir=args.data_dir)
        except (OSError, ValueError) as retry_error:
            print(f"\n  Impossibile avviare Caos: {retry_error}\n", file=sys.stderr)
            return 1
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"\n  CAOS — Ogni file, al suo posto.\n\n  Apri {url}\n  Premi Ctrl+C per chiudere l'app.\n", flush=True)
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    def request_stop(_signum, _frame):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, request_stop)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\n  Chiusura in corso: attendo eventuali spostamenti…", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
