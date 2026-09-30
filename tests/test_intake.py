import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from intake import prepare_submission, local_preview

class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_csv_profile_has_no_raw_rows(self):
        path=self.root/'sales.csv'
        path.write_text('customer,value\nAlice,10\nBob,20\nBob,20\n')
        result=prepare_submission(path,'What changed?')
        self.assertEqual(result['profile']['rows_analyzed'],3)
        self.assertEqual(result['profile']['duplicate_rows'],1)
        self.assertNotIn('Alice',str(result))
        self.assertIn('no AI requests made',local_preview(result))
    def test_row_limit_is_disclosed(self):
        path=self.root/'sample.csv';path.write_text('value\n1\n2\n3\n')
        with patch('intake.MAX_ROWS',2):result=prepare_submission(path,'summary')
        self.assertTrue(result['profile']['row_limit_reached'])
        self.assertEqual(result['profile']['rows_analyzed'],2)
    def test_document_scope_and_question(self):
        path=self.root/'report.md';path.write_text('A long enough report with findings.')
        result=prepare_submission(path,'Explain limitations')
        self.assertEqual(result['question'],'Explain limitations')
        self.assertEqual(result['kind'],'document_excerpt')
    def test_document_truncation_is_disclosed(self):
        path=self.root/'report.txt';path.write_text('abcdefghijklmno')
        with patch('intake.MAX_CHARS',10):result=prepare_submission(path,'summary')
        self.assertEqual(len(result['text']),10)
        self.assertTrue(any('first 10' in x for x in result['limitations']))
    def test_empty_file_fails(self):
        path=self.root/'report.txt';path.write_text('')
        with self.assertRaises(ValueError):prepare_submission(path,'summary')
    def test_unknown_format_fails(self):
        path=self.root/'report.exe';path.write_text('not an executable')
        with self.assertRaises(ValueError):prepare_submission(path,'summary')

if __name__=='__main__':unittest.main()
