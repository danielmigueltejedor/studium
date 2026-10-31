"""Package original Studium Python sources for the browser authoring worker."""

import argparse
import base64
import hashlib
import io
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=root.parents[1] / 'src' / 'studium')
args = parser.parse_args()
source = args.source.resolve()
if not (source / 'storage' / 'init_project.py').is_file():
    raise SystemExit('Provide the original src/studium directory with --source.')
manifest = {}
archive = io.BytesIO()
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
    for path in sorted(source.rglob('*.py')):
        name = 'studium/' + path.relative_to(source).as_posix()
        content = path.read_bytes()
        manifest[name] = hashlib.sha256(content).hexdigest()
        info = zipfile.ZipInfo(name, date_time=(2026, 10, 26, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        bundle.writestr(info, content)
metadata = {
    'repository': 'https://github.com/danielmigueltejedor/studium',
    'revision': 'f7bc7310507b83bb23738511843fc7c7f1b6c96e',
    'license': 'Apache-2.0',
    'files': manifest,
}
(root / 'public' / 'studium-core.js').write_text(
    '// Original, pinned Studium framework. Apache-2.0; see studium-framework-LICENSE.txt.\n'
    + 'export const CORE_MANIFEST=' + json.dumps(metadata) + ';\n'
    + 'export const CORE_ARCHIVE=' + json.dumps(base64.b64encode(archive.getvalue()).decode()) + ';\n'
)
print(f'Packaged {len(manifest)} original Python modules ({len(archive.getvalue())} ZIP bytes).')
