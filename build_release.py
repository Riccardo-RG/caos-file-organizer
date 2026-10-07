"""Build a portable source release, without personal data or saved operations."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from server import VERSION


def build():
    root = Path(__file__).resolve().parent
    release = '.'.join(VERSION.split('.')[:2])
    output = root / 'dist' / f'Caos-{release}.zip'
    output.parent.mkdir(exist_ok=True)
    files = [root / name for name in ('server.py', 'organizer.py', 'Avvia Caos.command',
             'README.md', 'VERIFICATION.md', '.gitignore', 'build_release.py',
             '.github/workflows/ci.yml')]
    files += sorted((root / 'web').glob('*'))
    files += sorted((root / 'tests').glob('test_*.py'))
    files += sorted((root / 'docs' / 'screenshots').glob('*.jpg'))
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for path in files:
            if path.is_file():
                archive.write(path, 'Caos/' + path.relative_to(root).as_posix())
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Archivio non valido')
        for path in files:
            if path.is_file():
                assert archive.read('Caos/' + path.relative_to(root).as_posix()) == path.read_bytes()
    print(f'Creato {output} ({output.stat().st_size:,} byte)')
    return output


if __name__ == '__main__':
    build()
