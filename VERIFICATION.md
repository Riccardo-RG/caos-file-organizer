# Release verification

This document records the validation scope for Caos 1.2.0. It describes observed behavior, not a guarantee that every filesystem, browser, or external file modification is covered.

## Automated checks

The Python suite covers the file engine, local HTTP API, folder browser, startup and shutdown, and portable release. Tests use disposable files and temporary state directories.

Local result: **72 tests passed, none skipped**, on macOS with Python 3.14.6. JavaScript syntax checks passed for all four scripts.

```sh
python3 build_release.py
python3 -m unittest discover -s tests -v
node --check web/app.js
node --check web/theme.js
node --check web/i18n.js
node --check web/messages.js
```

Building first enables the distribution test, which checks source contents against the ZIP byte for byte, checks launcher permissions, and excludes local history and demo data. In a source-only checkout without a built ZIP, that test is skipped.

Coverage includes:

- Preview without mutation, grouping, name normalization, numbering, and partial selection.
- Existing destinations and collisions introduced after preview, including case differences.
- SHA-256 content preservation and restoration of original paths and metadata.
- Persistent history, undo after restart, and multiple operations.
- Changed files, symbolic links, invalid paths, replaced directories, and protected locations.
- Interruptions around atomic moves, partial rollback, and later recovery.
- Files replaced by an external editor during an operation.
- HTTP session tokens, Origin and Host checks, JSON validation, and static routes.
- Folder browsing without filesystem mutations, including blocked application and photo-library paths.
- Unusual POSIX names and temporarily unavailable source folders.
- Concurrent startup, occupied ports, idle connections, termination, and completion of active file operations before shutdown.
- Loopback startup without reverse-DNS lookup, including environments with unavailable DNS resolution.

The GitHub workflow runs the suite on macOS and Ubuntu with Python 3.10 and 3.14. See the repository's Actions tab for the result associated with a specific commit.

## Browser checks

The local macOS browser checks use disposable demo files only. No personal files are organized during validation.

The original workflow was exercised with a partial selection of seven files and a recursive operation on nine files, including type/month grouping and sequence naming. Undo restored all original paths and SHA-256 hashes.

For the dark theme, an additional eight-file organize/undo cycle restored all nine files in the fixture, including the unselected nested file. The theme was checked on the setup form, preview, confirmation dialog, and history. The dark preference survived a page reload. Screenshots in `docs/screenshots/` contain only generated demo data.

Theme bootstrap checks also cover system appearance changes, explicit theme overrides, cross-tab storage changes, invalid preferences, and unavailable browser storage.

The English interface was exercised through preview, partial selection, confirmation, completion, history, and undo. Switching between Italian and English preserved the preview, selected files, form values, and literal file paths. A seven-file operation restored all nine fixture paths and hashes after undo. The restored preview message updated correctly in both languages, and the English preference survived a page reload. No browser JavaScript warnings or errors were recorded during this flow.

Responsive checks covered narrow, intermediate, and desktop layouts. Focus indicators remain separated from their labels, long paths wrap inside cards and dialogs, confirmation buttons wrap on small screens, and preview scrolling leaves room for the sticky toolbar. Synthetic long folder and file names produced no page overflow at the narrowest tested layout (291 CSS pixels). A file literally named `Documenti` retained its name when the language changed. Folder-picker error states were checked in English.

Translation checks covered all 239 interface strings and 68 backend messages, plus parameterized errors. Additional checks preserved unusual Unicode, punctuation, and line breaks in filenames and paths.

## Portable ZIP

The final `Caos-1.2.zip` was extracted with macOS `ditto` into a temporary directory. Its executable launcher started the app on an available port, the API reported version 1.2.0, and all seven web resources loaded successfully. Termination returned exit code 0.

## Platform scope

The primary local validation platform is macOS with Python 3.14.6. Linux receives automated engine, HTTP, startup, and packaging coverage through CI; it has not received the same interactive desktop validation. Windows is unsupported.

Moves depend on the operating system's atomic rename-without-replacement primitive. Unsupported filesystems return an error. Undo requires the saved journal and unchanged files at their expected locations; it is not a content backup.
