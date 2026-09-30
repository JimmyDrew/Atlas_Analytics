"""Local report extraction and bounded tabular profiling for the desktop interface."""
import json
from pathlib import Path
import pandas as pd

MAX_ROWS = 100_000
MAX_CHARS = 40_000
MAX_BYTES = 30 * 1024 * 1024

def prepare_submission(path, question):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Choose a file smaller than 30 MB.')
    evidence = {'source_name': path.name, 'question': question.strip(), 'limitations': []}
    ext = path.suffix.lower()
    if ext in ('.csv', '.xlsx'):
        if ext == '.csv':
            df = pd.read_csv(path, nrows=MAX_ROWS + 1)
            scope = 'CSV'
        else:
            with pd.ExcelFile(path) as book:
                sheet = book.sheet_names[0]
                df = pd.read_excel(book, sheet_name=sheet, nrows=MAX_ROWS + 1)
                scope = f'First worksheet only: {sheet}'
                evidence['limitations'].append(f'Workbook has {len(book.sheet_names)} worksheet(s); only {sheet} is profiled.')
        truncated = len(df) > MAX_ROWS
        df = df.iloc[:MAX_ROWS]
        if df.empty or not len(df.columns):
            raise ValueError('The selected table has no data rows.')
        if len(df.columns) > 100:
            raise ValueError('Select a table with at most 100 columns.')
        numeric = df.select_dtypes(include='number')
        summary = json.loads(numeric.describe().to_json()) if len(numeric.columns) else {}
        evidence.update({'kind': 'table_profile', 'scope': scope,
            'profile': {'rows_analyzed': len(df), 'row_limit_reached': truncated,
                'columns': [str(c) for c in df.columns],
                'dtypes': {str(k): str(v) for k,v in df.dtypes.items()},
                'missing': {str(k): int(v) for k,v in df.isna().sum().items()},
                'duplicate_rows': int(df.duplicated().sum()), 'numeric_summary': summary}})
        evidence['limitations'] += ['Numeric fields may include identifiers; no units or business meanings are assumed.',
            'Only column names and aggregate statistics are sent to AI; no raw rows. This profile does not run the three industry-specific SQL analyses.']
        if truncated:
            evidence['limitations'].append(f'Only the first {MAX_ROWS:,} rows are analyzed; this is not a representative random sample.')
    elif ext in ('.pdf', '.txt', '.md', '.json'):
        if ext == '.pdf':
            from pypdf import PdfReader
            reader = PdfReader(path)
            if reader.is_encrypted:
                raise ValueError('Use an unencrypted PDF.')
            pages = reader.pages[:30]
            text = '\n\n'.join(f'[Page {i+1}]\n' + (p.extract_text() or '') for i,p in enumerate(pages))
            evidence['limitations'].append(f'Text extracted from {len(pages)} of {len(reader.pages)} PDF pages. Images, charts and layout are not analyzed.')
        else:
            text = path.read_text(encoding='utf-8-sig')
        if len(text.strip()) < 10:
            raise ValueError('No usable text found. Scanned PDFs need OCR first.')
        evidence.update({'kind': 'document_excerpt', 'text': text[:MAX_CHARS],
                         'characters_extracted': len(text), 'characters_submitted': min(len(text), MAX_CHARS)})
        evidence['limitations'].append('Document claims are not independently verified against source records.')
        if len(text) > MAX_CHARS:
            evidence['limitations'].append(f'Only the first {MAX_CHARS:,} characters are included.')
    else:
        raise ValueError('Supported formats: CSV, XLSX, PDF, TXT, MD and JSON.')
    return evidence

def local_preview(evidence):
    lines = ['LOCAL PREVIEW - no AI requests made', '', f"File: {evidence['source_name']}",
             f"Question: {evidence['question'] or '(none)'}", '',
             'This preview summarizes the file. Use Ask AI Team for an answer to your question.', '']
    if evidence['kind'] == 'table_profile':
        p = evidence['profile']
        lines += [f"Rows analyzed: {p['rows_analyzed']:,}", f"Columns: {len(p['columns'])}",
                  f"Duplicate rows: {p['duplicate_rows']:,}", '', 'Missing values by column:']
        lines += [f'  {k}: {v:,}' for k,v in p['missing'].items()]
        lines += ['', 'Numeric summary:', json.dumps(p['numeric_summary'], indent=2)]
    else:
        lines += [f"Characters included: {evidence['characters_submitted']:,}", '', evidence['text']]
    lines += ['', 'SCOPE AND LIMITATIONS'] + ['- ' + s for s in evidence['limitations']]
    return '\n'.join(lines)
