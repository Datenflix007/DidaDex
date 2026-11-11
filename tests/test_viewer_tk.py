"""Tests without network or graphical desktop. Run: python -m unittest discover -s tests"""
import json
import tempfile
import unittest
from pathlib import Path

from crawledDataViewer.viewer_tk import (
    descriptive_class, scan_jsonl, load_document, read_labels,
    write_labels, label_category,
)


class ViewerDataTests(unittest.TestCase):
    def test_quality_classes(self):
        self.assertEqual(descriptive_class({'quality_score': 15}), 'Unterrichtsmaterial')
        self.assertEqual(descriptive_class({'quality_score': 8}), 'Prüfen')
        self.assertEqual(descriptive_class({'quality_score': 'invalid'}), 'Unbrauchbar')

    def test_scan_offsets_and_invalid_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'crawl.jsonl'
            docs = [
                {'id': 'one', 'url': 'https://test.example/1', 'title': 'Material A',
                 'quality_score': 10, 'text': 'Volltext' * 2000,
                 'material_links': ['https://test.example/1.pdf']},
                {'id': 'two', 'title': 'Material B', 'text': 'Noch ein Text'},
            ]
            with path.open('w', encoding='utf-8') as f:
                f.write(json.dumps(docs[0], ensure_ascii=False) + '\n')
                f.write('kein json\n')
                f.write(json.dumps(docs[1], ensure_ascii=False) + '\n')
            rows, invalid, processed = scan_jsonl(path)
            self.assertEqual((len(rows), invalid, processed), (2, 1, 3))
            self.assertEqual(rows[0]['material_count'], 1)
            self.assertEqual(len(rows[0]['excerpt']), 6000)
            self.assertEqual(load_document(path, rows[1]['offset']), docs[1])

    def test_labels_preserve_old_streamlit_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            original = {'raw-0': {'category': 'Prüfen', 'url': 'https://test.example/1', 'note': 'Beispiel'}}
            write_labels(folder, original)
            loaded = read_labels(folder)
            self.assertEqual(label_category(loaded, 'raw-0'), 'Prüfen')
            loaded['new-key'] = {'category': 'Unterrichtsmaterial', 'url': 'https://test.example/2'}
            write_labels(folder, loaded)
            self.assertEqual(read_labels(folder)['raw-0']['note'], 'Beispiel')


if __name__ == '__main__':
    unittest.main()
