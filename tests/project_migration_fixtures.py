"""Build a format v1 lightweight fixture from the same source as a format v2 bundle."""

import json
from zipfile import ZipFile


def write_legacy_lightweight(lightweight, legacy):
    with ZipFile(lightweight) as current, ZipFile(legacy, 'w') as old:
        manifest = json.loads(current.read('bundle.json'))
        assert manifest['version'] == 2 and manifest['source_included'] is False
        old.writestr('bundle.json', json.dumps({
            'format': manifest['format'], 'version': 1, 'source_included': False,
        }))
        project = json.loads(current.read('project.json'))
        source = next(item for item in project['media'] if item['id'] == project['source_id'])
        source.pop('sha256')
        old.writestr('project.json', json.dumps(project, ensure_ascii=False))
        for entry in current.infolist():
            if entry.filename not in ('bundle.json', 'project.json', 'agent-tasks.json'):
                old.writestr(entry.filename, current.read(entry))
