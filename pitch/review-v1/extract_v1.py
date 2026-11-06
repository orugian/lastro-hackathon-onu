from pathlib import Path
from datetime import datetime, timezone
import json
import hashlib
import pymupdf

source = Path(r'C:\Users\orugi\.dsh\attachments\v1\files\60\60ee5e97add03d5f62f93d150280e7b0fd5b8b495816fb888be87b44d39aea36\Pitch Lastro ONU.pdf')
out = Path(__file__).parent / ('extraction-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
out.mkdir(parents=True, exist_ok=False)
doc = pymupdf.open(source)
pages = []
texts = []
for i, page in enumerate(doc, 1):
    text = page.get_text('text', sort=True)
    blocks = page.get_text('dict')
    entry = {'page': i, 'width_pt': page.rect.width, 'height_pt': page.rect.height, 'text': text, 'blocks': []}
    for block in blocks['blocks']:
        if block['type'] == 0:
            entry['blocks'].append({'bbox': block['bbox'], 'lines': [{'bbox': ln['bbox'], 'spans': [{'text': s['text'], 'font': s['font'], 'size': s['size'], 'color': s['color']} for s in ln['spans']]} for ln in block['lines']]})
    pages.append(entry)
    texts.append(f'## Página {i}\n\n{text}')
    pix = page.get_pixmap(matrix=pymupdf.Matrix(1.25, 1.25), alpha=False)
    pix.save(out / f'page-{i:02}.png')
result = {'source': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'page_count': len(doc), 'metadata': doc.metadata, 'pages': pages}
(out / 'v1-structure.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
(out / 'v1-text.md').write_text('# Extração V1 — Pitch Lastro ONU\n\n' + '\n\n'.join(texts), encoding='utf-8')
print(out.resolve())
print('Pages:', len(doc))
