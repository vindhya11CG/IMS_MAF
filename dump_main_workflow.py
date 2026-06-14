import fitz
import pathlib

path = pathlib.Path('docs') / 'main_workflow_doc.pdf'
doc = fitz.open(path)
for i in range(min(4, len(doc))):
    print('=== page', i+1, '===')
    print(doc[i].get_text())
    print('--- END PAGE', i+1, '---')
doc.close()
