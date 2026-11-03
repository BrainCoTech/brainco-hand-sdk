#!/usr/bin/env python3
"""Package only the maintained public CAN FD diagnostic files."""
import argparse
import hashlib
import zipfile
from pathlib import Path

FILES = (
    'README.zh.md', 'CANFD_PROTOCOL.zh.md',
    'direct/README.zh.md', 'direct/canfd_direct.py', 'direct/frame_reference.txt',
    'sdk/README.zh.md', 'sdk/canfd_sdk.py',
    'direct/test_canfd_direct.py', 'sdk/test_canfd_sdk.py', 'package.py',
)


def package(output):
    root = Path(__file__).resolve().parent
    content = {name: (root / name).read_bytes() for name in FILES}
    content['SHA256SUMS'] = ''.join(
        f'{hashlib.sha256(data).hexdigest()}  {name}\n'
        for name, data in content.items()
    ).encode('utf-8')
    # Fixed metadata makes the same sources produce the same archive bytes.
    with output.open('xb') as handle:
        with zipfile.ZipFile(handle, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in content.items():
                entry = zipfile.ZipInfo('revo2_canfd_diagnostics/' + name, (2020, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, data)
    print(f'{hashlib.sha256(output.read_bytes()).hexdigest()}  {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('revo2_canfd_diagnostics.zip'))
    package(parser.parse_args().output)
