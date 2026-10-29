"""Package pinned native Studium planning modules; no source document text involved."""

import importlib
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'vendor'))
profile_module = importlib.import_module('studium.authoring.depth.profiles')
files = {}
for path in [
    'studium/__init__.py',
    'studium/authoring/__init__.py',
    'studium/authoring/depth/__init__.py',
    'studium/authoring/depth/profiles.py',
    'studium/authoring/depth/length.py',
]:
    files['/' + path] = (root / 'vendor' / path).read_text()
profiles = {
    key: {
        **profile_module.profile_requirements(value),
        'pages_per_concept': value.pages_per_concept,
        'derivation_pages_per_item': value.derivation_pages_per_item,
    }
    for key, value in profile_module.PROFILES.items()
}
metadata = {
    'repository': 'https://github.com/danielmigueltejedor/studium',
    'revision': 'f7bc7310507b83bb23738511843fc7c7f1b6c96e',
    'modules': ['authoring.depth.profiles', 'authoring.depth.length'],
    'license': 'Apache-2.0',
}
(root / 'public/studium-python.js').write_text(
    '// Generated from pinned, unmodified upstream Studium Python modules. Apache-2.0.\n'
    + 'export const FRAMEWORK=' + json.dumps(metadata) + ';\n'
    + 'export const PROFILES=' + json.dumps(profiles) + ';\n'
    + 'export const PYTHON_FILES=' + json.dumps(files) + ';\n'
)
print('Native Studium depth modules packaged at ' + str(metadata['revision'])[:12])
