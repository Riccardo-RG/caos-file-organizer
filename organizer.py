"""Conservative, journalled file organisation using only the Python standard library.

User files are moved with the operating system's atomic no-replace rename. This
preserves their bytes and metadata and never replaces an existing path. Mounted
subtrees are deliberately not crossed. All paths below the selected root are
opened without following symlinks.
"""

from __future__ import annotations

import contextlib
import ctypes
import datetime as dt
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import threading
import unicodedata
import uuid

try:
    import fcntl
except ImportError:  # The bundled macOS/Linux launcher uses fcntl.
    fcntl = None


class OrganizerError(ValueError):
    """A readable validation or file-safety error."""


CATEGORIES = {
    "images": ("Immagini", "jpg jpeg png gif webp heic heif tif tiff bmp svg avif raw cr2 cr3 nef arw dng ico"),
    "documents": ("Documenti", "pdf doc docx odt rtf txt md pages xls xlsx ods csv tsv numbers ppt pptx odp key epub mobi tex"),
    "archives": ("Archivi", "zip rar 7z tar gz bz2 xz tgz zst iso dmg"),
    "audio": ("Audio", "mp3 wav flac aac m4a ogg opus aiff aif wma mid midi"),
    "video": ("Video", "mp4 mov mkv avi webm m4v mpg mpeg wmv flv mts m2ts"),
    "code": ("Codice", "py js ts jsx tsx html css scss json yaml yml xml toml ini sh bash zsh c h cpp hpp rs go java swift kt sql ipynb rb php vue svelte"),
    "other": ("Altro", ""),
}
_EXTENSIONS = {ext: key for key, (_, extensions) in CATEGORIES.items() for ext in extensions.split()}
_OUTPUT_NAMES = {label.casefold() for label, _ in CATEGORIES.values()}
_BUNDLE_SUFFIXES = {".app", ".bundle", ".framework", ".photoslibrary", ".photolibrary", ".musiclibrary", ".pages", ".numbers", ".key"}
_INCOMPLETE_SUFFIXES = {".crdownload", ".download", ".part", ".partial", ".tmp"}
_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
_SCHEMA = 1


def _rename_exclusive(source_fd, source_name, destination_fd, destination_name):
    """No check-then-rename or link-then-unlink fallback: both can lose data."""
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        function = getattr(library, "renameatx_np", None)
        flag = 0x00000004  # RENAME_EXCL, Darwin sys/stdio.h.
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        flag = 1  # RENAME_NOREPLACE, Linux rename(2).
    else:
        function = None
        flag = 0
    if function is None:
        raise OrganizerError("Questo sistema non offre lo spostamento atomico senza sovrascrittura richiesto dall'app.")
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    if function(source_fd, os.fsencode(source_name), destination_fd, os.fsencode(destination_name), flag) != 0:
        error = ctypes.get_errno()
        if error in (errno.ENOSYS, errno.ENOTSUP, errno.EINVAL):
            raise OrganizerError("Questo filesystem non supporta lo spostamento sicuro senza sovrascrittura. Nessun file è stato sostituito.")
        raise OSError(error, os.strerror(error), source_name)


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _snapshot(info):
    return {"dev": info.st_dev, "ino": info.st_ino, "size": info.st_size,
            "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns,
            "mode": info.st_mode}


def _identity(info):
    return {"dev": info.st_dev, "ino": info.st_ino}


def _same_identity(info, expected):
    return info.st_dev == expected["dev"] and info.st_ino == expected["ino"]


def _matches_snapshot(actual, expected):
    # ctime also changes on a rename or on another hard link to the same inode.
    # Identity, bytes, modification time and mode must still match. This permits
    # reversing successive operations without mistaking our own renames for edits.
    return all(actual[key] == expected[key] for key in ("dev", "ino", "size", "mtime_ns", "mode"))


def _sync_directory(fd):
    try:
        os.fsync(fd)
    except OSError as exc:
        # Some removable filesystems cannot fsync a directory descriptor. Their
        # atomic rename still provides the required no-overwrite guarantee.
        if exc.errno not in (errno.EINVAL, errno.ENOTSUP):
            raise


def _parts(relative):
    if not isinstance(relative, str) or not relative or "\x00" in relative or "\\" in relative:
        raise OrganizerError("Percorso del file non valido.")
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part in ("", ".", "..") for part in relative.split("/")):
        raise OrganizerError("Il percorso esce dalla cartella selezionata.")
    return path.parts


def _hash_fd(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


@contextlib.contextmanager
def _parent(root_fd, relative, create=False, on_created=None):
    parts = _parts(relative)
    current = os.dup(root_fd)
    try:
        for index, name in enumerate(parts[:-1]):
            try:
                child = os.open(name, _DIR_FLAGS, dir_fd=current)
            except FileNotFoundError:
                if not create:
                    raise
                created = False
                try:
                    os.mkdir(name, mode=0o755, dir_fd=current)
                    created = True
                except FileExistsError:
                    pass
                child = os.open(name, _DIR_FLAGS, dir_fd=current)
                if created and on_created:
                    on_created({"path": "/".join(parts[:index + 1]), **_identity(os.fstat(child))})
            os.close(current)
            current = child
        yield current, parts[-1]
    finally:
        os.close(current)


def _lstat(root_fd, relative):
    try:
        with _parent(root_fd, relative) as (parent_fd, name):
            return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _inspect(root_fd, relative):
    with _parent(root_fd, relative) as (parent_fd, name):
        fd = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise OrganizerError(f"Il file non è un file regolare: {relative}")
            digest = _hash_fd(fd)
            after = os.fstat(fd)
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if _snapshot(before) != _snapshot(after) or _snapshot(current) != _snapshot(after):
                raise OrganizerError(f"Il file è cambiato durante la lettura: {relative}")
            return _snapshot(after), digest
        finally:
            os.close(fd)


def _clean_name(name):
    path = Path(name)
    stem = unicodedata.normalize("NFC", path.stem).lower()
    stem = re.sub(r"[^\w\s-]", "", stem, flags=re.UNICODE)
    stem = re.sub(r"[\s_-]+", "-", stem).strip(".-") or "file"
    return stem + path.suffix.lower()


def _safe_prefix(prefix):
    if not isinstance(prefix, str):
        raise OrganizerError("Il prefisso deve essere un testo.")
    prefix = unicodedata.normalize("NFC", prefix.strip())
    if not prefix or len(prefix.encode("utf-8")) > 100 or any(c in prefix for c in '/\\\x00') or prefix in (".", ".."):
        raise OrganizerError("Scegli un prefisso da 1 a 100 byte, senza barre.")
    if any(ord(c) < 32 for c in prefix) or prefix.startswith("."):
        raise OrganizerError("Il prefisso non può essere nascosto o contenere caratteri di controllo.")
    return prefix


def _options(options):
    if not isinstance(options, dict):
        raise OrganizerError("Le opzioni non sono valide.")
    result = {"organize": options.get("organize", True), "grouping": options.get("grouping", "type"),
              "rename": options.get("rename", "keep"), "prefix": options.get("prefix", "file"),
              "recursive": options.get("recursive", False), "categories": options.get("categories", list(CATEGORIES))}
    if type(result["organize"]) is not bool or type(result["recursive"]) is not bool:
        raise OrganizerError("Le opzioni di scansione non sono valide.")
    if result["grouping"] not in ("type", "month", "type_month") or result["rename"] not in ("keep", "clean", "sequence"):
        raise OrganizerError("La modalità di organizzazione o rinomina non è valida.")
    if not isinstance(result["categories"], list) or any(not isinstance(c, str) or c not in CATEGORIES for c in result["categories"]):
        raise OrganizerError("La selezione delle categorie non è valida.")
    if result["rename"] == "sequence":
        result["prefix"] = _safe_prefix(result["prefix"])
    return result


class Organizer:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.plans_dir = self.data_dir / "plans"
        self.operations_dir = self.data_dir / "operations"
        self.plans_dir.mkdir(exist_ok=True, mode=0o700)
        self.operations_dir.mkdir(exist_ok=True, mode=0o700)
        self._mutex = threading.RLock()
        with self._locked():
            self._recover()

    @contextlib.contextmanager
    def _locked(self):
        with self._mutex:
            lock_fd = os.open(self.data_dir / "lock", os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                if fcntl:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX)
                yield
            finally:
                if fcntl:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)

    def _write(self, path, value):
        temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with open(temporary, "x", encoding="utf-8") as handle:
                os.chmod(temporary, 0o600)
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, _DIR_FLAGS)
            try:
                _sync_directory(directory)
            finally:
                os.close(directory)
        finally:
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()

    def _read(self, directory, item_id):
        if not isinstance(item_id, str) or not re.fullmatch(r"[0-9a-f]{32}", item_id):
            raise OrganizerError("Identificativo non valido.")
        try:
            with open(directory / (item_id + ".json"), encoding="utf-8") as handle:
                value = json.load(handle)
        except FileNotFoundError:
            raise OrganizerError("Anteprima o operazione non trovata. Crea una nuova anteprima.") from None
        except (OSError, ValueError):
            raise OrganizerError("Il registro non è leggibile. Nessun file è stato modificato.") from None
        if not isinstance(value, dict) or value.get("schema") != _SCHEMA or value.get("id") != item_id:
            raise OrganizerError("Il registro dell'operazione non è valido.")
        try:
            if not isinstance(value["root"], str) or not Path(value["root"]).is_absolute():
                raise ValueError
            if not isinstance(value["created_at"], str):
                raise ValueError
            if any(type(value["root_identity"][key]) is not int for key in ("dev", "ino")):
                raise ValueError
            if directory == self.operations_dir:
                if value["state"] not in ("applying", "applied", "partial", "failed", "undoing", "undone", "undo_partial"):
                    raise ValueError
                if not isinstance(value["entries"], list) or not isinstance(value["created_dirs"], list):
                    raise ValueError
                for item in value["entries"]:
                    if not isinstance(item["id"], str) or type(item["size"]) is not int or item["category"] not in CATEGORIES:
                        raise ValueError
                    _parts(item["source"])
                    _parts(item["destination"])
                    if item["state"] not in ("pending", "moving", "linked", "moved", "restoring", "restored_linked", "undone", "duplicated", "conflict"):
                        raise ValueError
                    if not isinstance(item["digest"], str) or not re.fullmatch("[0-9a-f]{64}", item["digest"]):
                        raise ValueError
                    if any(type(item["initial_snapshot"][key]) is not int for key in ("dev", "ino", "size", "mtime_ns", "ctime_ns", "mode")):
                        raise ValueError
                for item in value["created_dirs"]:
                    _parts(item["path"])
                    if any(type(item[key]) is not int for key in ("dev", "ino")):
                        raise ValueError
            else:
                if not isinstance(value["files"], list):
                    raise ValueError
                for item in value["files"]:
                    if not isinstance(item["id"], str) or type(item["size"]) is not int or item["category"] not in CATEGORIES:
                        raise ValueError
                    if item["status"] not in ("ready", "unchanged", "skipped"):
                        raise ValueError
                    if item["status"] != "skipped":
                        _parts(item["source"])
                        _parts(item["destination"])
                    elif any(not isinstance(item[key], str) or not item[key] or "\x00" in item[key]
                             for key in ("source", "destination")):
                        raise ValueError
                    if item["status"] == "ready":
                        if any(type(item["_snapshot"][key]) is not int for key in ("dev", "ino", "size", "mtime_ns", "ctime_ns", "mode")):
                            raise ValueError
                        if not isinstance(item["_digest"], str) or not re.fullmatch("[0-9a-f]{64}", item["_digest"]):
                            raise ValueError
        except (KeyError, TypeError, ValueError, AttributeError):
            raise OrganizerError("Il registro dell'operazione è incompleto o danneggiato. Nessun file è stato modificato.") from None
        return value

    def _save_operation(self, operation):
        self._write(self.operations_dir / (operation["id"] + ".json"), operation)

    def _root(self, root):
        if not isinstance(root, str) or not root or "\x00" in root:
            raise OrganizerError("Scegli una cartella valida.")
        candidate = Path(root).expanduser()
        if not candidate.is_absolute():
            raise OrganizerError("Inserisci il percorso completo della cartella.")
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            raise OrganizerError("La cartella non esiste o non è accessibile.") from None
        if candidate.absolute() != resolved:
            raise OrganizerError("Seleziona la cartella reale, senza collegamenti simbolici nel percorso.")
        if any(part.suffix.lower() in _BUNDLE_SUFFIXES for part in (resolved, *resolved.parents)):
            raise OrganizerError("Le librerie Foto e i pacchetti applicazione non possono essere riordinati. Scegli una cartella di file o immagini esportate.")
        protected = [Path("/"), Path("/System"), Path("/Library"), Path("/Applications"),
                     Path("/bin"), Path("/sbin"), Path("/usr"), Path("/etc"), Path("/dev"),
                     Path("/proc"), Path("/sys"), Path("/private/etc"), Path("/private/var/db"), Path("/private/var/root"),
                     Path.home() / "Library"]
        if resolved in (Path("/"), Path("/private"), Path("/private/var")) or any(resolved == path or path in resolved.parents for path in protected[1:]):
            raise OrganizerError("Le cartelle di sistema non possono essere organizzate. Seleziona Download, Foto o Documenti.")
        if resolved == self.data_dir or self.data_dir in resolved.parents:
            raise OrganizerError("La cartella dei registri dell'app non può essere organizzata.")
        try:
            fd = os.open(resolved, _DIR_FLAGS)
        except OSError:
            raise OrganizerError("Il percorso deve indicare una cartella accessibile.") from None
        return resolved, fd

    @contextlib.contextmanager
    def _operation_root(self, operation):
        # A saved root must still name exactly the original directory, without a
        # newly introduced symlink at any component.
        path = Path(operation["root"])
        try:
            if path.resolve(strict=True) != path:
                raise OrganizerError("La cartella è stata sostituita da un collegamento. Operazione annullata.")
            fd = os.open(path, _DIR_FLAGS)
        except OSError:
            raise OrganizerError("La cartella originale non è più disponibile.") from None
        try:
            if not _same_identity(os.fstat(fd), operation["root_identity"]):
                raise OrganizerError("La cartella originale è stata sostituita. Crea una nuova anteprima.")
            yield fd
        finally:
            os.close(fd)

    def _scan(self, root, root_fd, recursive):
        found = []
        root_device = os.fstat(root_fd).st_dev

        def walk(directory_fd, relative=""):
            try:
                names = sorted(os.listdir(directory_fd), key=lambda n: (n.casefold(), n))
            except OSError as exc:
                raise OrganizerError(f"Impossibile leggere la cartella {relative or '.'}: {exc.strerror}") from None
            for name in names:
                if name.startswith("."):
                    continue
                rel = f"{relative}/{name}" if relative else name
                full = root / rel
                if full == self.data_dir or self.data_dir in full.parents:
                    continue
                try:
                    info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if stat.S_ISLNK(info.st_mode):
                    continue
                if stat.S_ISDIR(info.st_mode):
                    if (not recursive or info.st_dev != root_device or Path(name).suffix.lower() in _BUNDLE_SUFFIXES
                            or name.casefold() in _OUTPUT_NAMES or re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", name)):
                        continue
                    try:
                        child = os.open(name, _DIR_FLAGS, dir_fd=directory_fd)
                    except OSError as exc:
                        raise OrganizerError(f"Impossibile leggere la sottocartella {rel}: {exc.strerror}") from None
                    try:
                        if not _same_identity(os.fstat(child), _identity(info)):
                            raise OrganizerError("Una cartella è cambiata durante la scansione. Ripeti l'anteprima.")
                        walk(child, rel)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode):
                    found.append((rel, info))
                    if len(found) > 100000:
                        raise OrganizerError("Questa cartella supera 100.000 file. Seleziona una sottocartella.")

        walk(root_fd)
        return sorted(found, key=lambda item: (item[0].casefold(), item[0]))

    def _available(self, root_fd, relative, source, reserved):
        if relative.casefold() in reserved:
            return False
        # Match existing names conservatively even on case-sensitive filesystems;
        # the same preview therefore also behaves safely on macOS volumes.
        with _parent(root_fd, relative) as (parent_fd, name):
            names = os.listdir(parent_fd)
            for existing in names:
                if existing.casefold() == name.casefold():
                    candidate = str(PurePosixPath(relative).with_name(existing))
                    return candidate == source and relative == source
        return True

    def _destination(self, root_fd, desired, source, reserved):
        # Missing parents are safe to create later. An existing symlink or regular
        # file in their place is never traversed or replaced.
        parts = _parts(desired)
        current = os.dup(root_fd)
        missing = False
        try:
            for name in parts[:-1]:
                try:
                    child = os.open(name, _DIR_FLAGS, dir_fd=current)
                except FileNotFoundError:
                    # A differing case may refer to the same folder on another
                    # volume; ask for an unambiguous destination instead.
                    if any(n.casefold() == name.casefold() for n in os.listdir(current)):
                        raise OrganizerError("Nome di cartella in conflitto (maiuscole/minuscole).")
                    missing = True
                    break
                os.close(current)
                current = child
        finally:
            os.close(current)
        base = PurePosixPath(desired)
        candidate = desired
        number = 2
        while True:
            available = candidate.casefold() not in reserved if missing else self._available(root_fd, candidate, source, reserved)
            if available:
                if len(PurePosixPath(candidate).name.encode("utf-8")) > 255:
                    raise OrganizerError("Il nome di destinazione è troppo lungo.")
                return candidate
            suffix = base.suffix
            stem = base.stem
            tail = f" ({number}){suffix}"
            while len((stem + tail).encode("utf-8")) > 255:
                stem = stem[:-1]
            candidate = str(base.with_name(stem + tail))
            number += 1

    def preview(self, root: str, options: dict):
        options = _options(options)
        with self._locked():
            resolved, root_fd = self._root(root)
            try:
                found = self._scan(resolved, root_fd, options["recursive"])
                reserved = set()
                files = []
                sequence = 0
                for index, (relative, info) in enumerate(found, start=1):
                    filename = PurePosixPath(relative).name
                    category = _EXTENSIONS.get(Path(filename).suffix.lower().lstrip("."), "other")
                    item = {"id": f"f{index:06d}", "source": relative, "destination": relative,
                            "category": category, "size": info.st_size, "status": "ready"}
                    files.append(item)
                    if category not in options["categories"]:
                        item.update(status="skipped", reason="Categoria esclusa.")
                        continue
                    if Path(filename).suffix.lower() in _INCOMPLETE_SUFFIXES:
                        item.update(status="skipped", reason="Download incompleto o file temporaneo.")
                        continue
                    if info.st_dev != os.fstat(root_fd).st_dev:
                        item.update(status="skipped", reason="File su un filesystem differente.")
                        continue
                    try:
                        snapshot, digest = _inspect(root_fd, relative)
                        if snapshot != _snapshot(info):
                            raise OrganizerError("Il file è cambiato durante la scansione.")
                        sequence += 1
                        if options["rename"] == "clean":
                            name = _clean_name(filename)
                        elif options["rename"] == "sequence":
                            name = f"{options['prefix']}-{sequence:03d}{Path(filename).suffix.lower()}"
                        else:
                            name = filename
                        if options["organize"]:
                            month = dt.datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m")
                            folder = {"type": CATEGORIES[category][0], "month": month,
                                      "type_month": f"{CATEGORIES[category][0]}/{month}"}[options["grouping"]]
                            desired = f"{folder}/{name}"
                        else:
                            desired = str(PurePosixPath(relative).with_name(name))
                        destination = self._destination(root_fd, desired, relative, reserved)
                        item.update(destination=destination, _snapshot=snapshot, _digest=digest)
                        if destination == relative:
                            item["status"] = "unchanged"
                        reserved.add(destination.casefold())
                    except (OSError, OrganizerError) as exc:
                        item.update(status="skipped", reason=f"File non elaborabile: {getattr(exc, 'strerror', None) or str(exc)}")
                summary = {"total": len(files), "ready": sum(x["status"] == "ready" for x in files),
                           "unchanged": sum(x["status"] == "unchanged" for x in files),
                           "skipped": sum(x["status"] == "skipped" for x in files),
                           "bytes": sum(x["size"] for x in files)}
                plan = {"schema": _SCHEMA, "id": uuid.uuid4().hex, "root": str(resolved), "created_at": _now(),
                        "root_identity": _identity(os.fstat(root_fd)), "options": options,
                        "files": files, "summary": summary}
                self._write(self.plans_dir / (plan["id"] + ".json"), plan)
                return {key: self._public_files(value) if key == "files" else value for key, value in plan.items()
                        if key not in ("schema", "root_identity")}
            finally:
                os.close(root_fd)

    @staticmethod
    def _public_files(files):
        return [{k: v for k, v in item.items() if not k.startswith("_")} for item in files]

    def _verify(self, root_fd, relative, expected, digest):
        try:
            snapshot, actual = _inspect(root_fd, relative)
        except (OSError, OrganizerError):
            raise OrganizerError(f"Il file è cambiato o non è accessibile: {relative}. Crea una nuova anteprima.") from None
        if not _matches_snapshot(snapshot, expected) or actual != digest:
            raise OrganizerError(f"Il file è stato modificato: {relative}. Crea una nuova anteprima.")

    def _assert_free(self, root_fd, relative):
        try:
            if self._destination(root_fd, relative, "", set()) != relative:
                raise OrganizerError(f"La destinazione è già occupata: {relative}. Crea una nuova anteprima.")
        except OSError:
            raise OrganizerError(f"La cartella di destinazione è cambiata o non è accessibile: {relative}.") from None

    def _record_directory(self, operation, info):
        operation["created_dirs"].append(info)
        self._save_operation(operation)

    def _move(self, root_fd, source, destination, expected, digest, operation, entry, restoring=False):
        self._verify(root_fd, source, expected, digest)
        entry["state"] = "restoring" if restoring else "moving"
        self._save_operation(operation)
        callback = None if restoring else lambda info: self._record_directory(operation, info)
        with _parent(root_fd, source) as (source_fd, source_name), \
                _parent(root_fd, destination, create=True, on_created=callback) as (destination_fd, destination_name):
            # One native syscall atomically moves the current source and refuses
            # an existing destination. Concurrent atomic saves cannot be deleted
            # by a later unlink because there is no separate unlink.
            try:
                _rename_exclusive(source_fd, source_name, destination_fd, destination_name)
            except OSError as exc:
                if exc.errno == errno.EXDEV:
                    raise OrganizerError("Il filesystem non permette uno spostamento sicuro fra questi percorsi.") from None
                raise
            moved = os.stat(destination_name, dir_fd=destination_fd, follow_symlinks=False)
            if not stat.S_ISREG(moved.st_mode) or not _same_identity(moved, expected):
                # An external replacement raced the atomic rename. Its bytes
                # remain at the destination; recovery exposes the conflict.
                raise OrganizerError(f"Il file è cambiato durante lo spostamento: {source}")
            _sync_directory(destination_fd)
            _sync_directory(source_fd)
            snapshot, actual_digest = _inspect(root_fd, destination)
            entry["state"] = "undone" if restoring else "moved"
            entry["restored_snapshot" if restoring else "destination_snapshot"] = snapshot
            self._save_operation(operation)
            if actual_digest != digest or not _matches_snapshot(snapshot, expected):
                raise OrganizerError(f"Il file è stato modificato durante lo spostamento: {destination}")

    def apply(self, plan_id: str, selected_ids: list[str] | None = None):
        with self._locked():
            self._recover()
            plan = self._read(self.plans_dir, plan_id)
            if plan.get("used_by"):
                raise OrganizerError("Questa anteprima è già stata utilizzata. Crea una nuova anteprima.")
            # Recheck current exclusions for previews saved by an older release.
            # Undo deliberately remains available for restoring old operations.
            _, checked_fd = self._root(plan["root"])
            os.close(checked_fd)
            ready = {item["id"]: item for item in plan["files"] if item["status"] == "ready"}
            if selected_ids is None:
                selected = set(ready)
            else:
                if not isinstance(selected_ids, list) or any(not isinstance(item, str) or item not in ready for item in selected_ids):
                    raise OrganizerError("La selezione contiene file non disponibili nell'anteprima.")
                selected = set(selected_ids)
            if not selected:
                raise OrganizerError("Seleziona almeno un file da sistemare.")
            entries = [{"id": item["id"], "source": item["source"], "destination": item["destination"],
                        "category": item["category"], "size": item["size"], "state": "pending",
                        "initial_snapshot": item["_snapshot"], "digest": item["_digest"]}
                       for item in plan["files"] if item["id"] in selected]
            with self._operation_root(plan) as root_fd:
                # Validate the complete selection before creating any directories.
                for entry in entries:
                    self._verify(root_fd, entry["source"], entry["initial_snapshot"], entry["digest"])
                    self._assert_free(root_fd, entry["destination"])
                operation = {"schema": _SCHEMA, "id": uuid.uuid4().hex, "plan_id": plan_id,
                             "state": "applying", "created_at": _now(), "root": plan["root"],
                             "root_identity": plan["root_identity"], "entries": entries, "created_dirs": []}
                self._save_operation(operation)
                plan["used_by"] = operation["id"]
                self._write(self.plans_dir / (plan_id + ".json"), plan)
                try:
                    for entry in entries:
                        self._move(root_fd, entry["source"], entry["destination"], entry["initial_snapshot"],
                                   entry["digest"], operation, entry)
                    operation["state"] = "applied"
                except (OSError, OrganizerError) as exc:
                    operation["error"] = f"Spostamento interrotto: {getattr(exc, 'strerror', None) or str(exc)}"
                    self._reconcile_entries(root_fd, operation)
                    # Best-effort rollback restores only unchanged, identifiable
                    # files. Anything requiring attention remains in the journal.
                    for entry in reversed(entries):
                        try:
                            self._restore_entry(root_fd, operation, entry)
                        except (OSError, OrganizerError) as rollback_error:
                            entry["error"] = str(rollback_error)
                    operation["state"] = "partial" if any(e["state"] not in ("pending", "undone") for e in entries) else "failed"
                    self._cleanup_dirs(root_fd, operation)
                self._save_operation(operation)
                return self._public_operation(operation)

    def _reconcile_entries(self, root_fd, operation):
        for entry in operation["entries"]:
            if entry["state"] not in ("moving", "linked", "restoring", "restored_linked"):
                continue
            previous = entry["state"]
            try:
                source = _lstat(root_fd, entry["source"])
                destination = _lstat(root_fd, entry["destination"])
                source_ok = bool(source and stat.S_ISREG(source.st_mode) and _same_identity(source, entry["initial_snapshot"]))
                destination_ok = bool(destination and stat.S_ISREG(destination.st_mode) and _same_identity(destination, entry["initial_snapshot"]))
                if source_ok and destination_ok:
                    # Native rename never leaves two names behind. A concurrent
                    # program created a hard link. Do not conditionally unlink:
                    # another atomic save could replace it before the unlink.
                    entry["state"] = "conflict"
                    entry["error"] = "Entrambi i percorsi esistono. Nessun file è stato eliminato; verifica manualmente i collegamenti."
                elif source_ok and destination is None:
                    entry["state"] = "undone" if previous in ("restoring", "restored_linked") else "pending"
                elif source is None and destination_ok:
                    entry["state"] = "moved"
                    entry["destination_snapshot"], _ = _inspect(root_fd, entry["destination"])
                elif source_ok and previous == "moving":
                    entry["state"] = "pending"  # Exclusive rename failed; destination belongs to someone else.
                elif destination_ok and previous == "restoring":
                    entry["state"] = "moved"  # A new original path blocked the attempted undo.
                elif source_ok and previous == "restoring":
                    entry["state"] = "undone"  # Undo succeeded; another program created a new destination.
                else:
                    entry["state"] = "conflict"
                    entry["error"] = "I percorsi sono cambiati durante l'operazione. Controlla i file manualmente."
            except (OSError, OrganizerError) as exc:
                entry["state"] = "conflict"
                entry["error"] = str(exc)

    def _preflight_restore(self, root_fd, entry):
        if entry["state"] in ("pending", "undone"):
            return
        if entry["state"] != "moved":
            raise OrganizerError(f"Il file richiede una verifica manuale: {entry['source']}")
        try:
            self._verify(root_fd, entry["destination"], entry["destination_snapshot"], entry["digest"])
        except OrganizerError:
            raise OrganizerError(f"Impossibile annullare: {entry['destination']} è stato modificato, spostato o rimosso.") from None
        self._assert_free(root_fd, entry["source"])

    def _restore_entry(self, root_fd, operation, entry):
        self._preflight_restore(root_fd, entry)
        if entry["state"] in ("pending", "undone"):
            return
        self._move(root_fd, entry["destination"], entry["source"], entry["destination_snapshot"],
                   entry["digest"], operation, entry, restoring=True)

    def _cleanup_dirs(self, root_fd, operation):
        for item in reversed(operation["created_dirs"]):
            try:
                with _parent(root_fd, item["path"]) as (parent_fd, name):
                    info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode) and _same_identity(info, item):
                        os.rmdir(name, dir_fd=parent_fd)  # Only succeeds if empty.
            except OSError:
                pass

    def undo(self, operation_id: str):
        with self._locked():
            self._recover()
            operation = self._read(self.operations_dir, operation_id)
            if operation["state"] == "undone":
                raise OrganizerError("Questa operazione è già stata annullata.")
            if operation["state"] not in ("applied", "partial", "undo_partial"):
                raise OrganizerError("Questa operazione non contiene modifiche annullabili.")
            with self._operation_root(operation) as root_fd:
                for entry in operation["entries"]:
                    self._preflight_restore(root_fd, entry)
                operation["state"] = "undoing"
                self._save_operation(operation)
                try:
                    for entry in reversed(operation["entries"]):
                        self._restore_entry(root_fd, operation, entry)
                    operation["state"] = "undone"
                    operation["undone_at"] = _now()
                    operation.pop("error", None)
                    self._cleanup_dirs(root_fd, operation)
                except (OSError, OrganizerError) as exc:
                    self._reconcile_entries(root_fd, operation)
                    operation["state"] = "undo_partial"
                    operation["error"] = f"Annullamento interrotto: {getattr(exc, 'strerror', None) or str(exc)}"
                self._save_operation(operation)
                return self._public_operation(operation)

    def _recover(self):
        for path in sorted(self.operations_dir.glob("*.json")):
            try:
                operation = self._read(self.operations_dir, path.stem)
            except OrganizerError:
                continue
            previous = operation.get("recovery_pending", operation["state"])
            if previous not in ("applying", "undoing") and operation["state"] in ("partial", "undo_partial"):
                if any(entry["state"] in ("moving", "linked", "restoring", "restored_linked") for entry in operation["entries"]):
                    previous = "undoing" if operation["state"] == "undo_partial" else "applying"
            if previous not in ("applying", "undoing"):
                continue
            try:
                with self._operation_root(operation) as root_fd:
                    self._reconcile_entries(root_fd, operation)
                states = [item["state"] for item in operation["entries"]]
                if previous == "applying":
                    operation["state"] = "applied" if all(s == "moved" for s in states) else (
                        "failed" if all(s in ("pending", "undone") for s in states) else "partial")
                else:
                    operation["state"] = "undone" if all(s in ("pending", "undone") for s in states) else "undo_partial"
                if operation["state"] not in ("applied", "undone"):
                    operation["error"] = "L'app è stata interrotta. I progressi sono conservati nel registro; puoi annullare le modifiche sicure."
                if operation["state"] in ("failed", "undone"):
                    with self._operation_root(operation) as root_fd:
                        self._cleanup_dirs(root_fd, operation)
                operation.pop("recovery_pending", None)
                if operation["state"] in ("applied", "undone"):
                    operation.pop("error", None)
            except (OSError, OrganizerError) as exc:
                operation["state"] = "partial" if previous == "applying" else "undo_partial"
                operation["recovery_pending"] = previous
                operation["error"] = str(exc)
            self._save_operation(operation)

    @staticmethod
    def _public_operation(operation, include_entries=True):
        value = {key: operation[key] for key in ("id", "state", "created_at", "root")}
        value["count"] = len(operation["entries"])
        value["moved"] = sum(e["state"] in ("moved", "duplicated") for e in operation["entries"])
        value["can_undo"] = operation["state"] in ("applied", "partial", "undo_partial")
        for key in ("error", "undone_at"):
            if key in operation:
                value[key] = operation[key]
        if include_entries:
            value["entries"] = [{k: v for k, v in e.items() if k not in
                                  ("initial_snapshot", "destination_snapshot", "restored_snapshot", "digest")}
                                 for e in operation["entries"]]
        return value

    def history(self):
        with self._locked():
            self._recover()
            operations = []
            for path in self.operations_dir.glob("*.json"):
                try:
                    operation = self._read(self.operations_dir, path.stem)
                    operations.append(self._public_operation(operation, include_entries=False))
                except (OrganizerError, KeyError, TypeError):
                    # A damaged record must never authorize filesystem changes.
                    continue
            return sorted(operations, key=lambda item: (item["created_at"], item["id"]), reverse=True)

    def details(self, operation_id: str):
        with self._locked():
            self._recover()
            return self._public_operation(self._read(self.operations_dir, operation_id))
