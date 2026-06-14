import fitz
import pathlib

base = pathlib.Path('docs')
for fname in ['main_workflow_doc.pdf', 'Business Requirements Document.pdf', 'Inventory_Management_System_Specification (1).pdf']:
    print('===', fname, '===')
    doc = fitz.open(base / fname)
    for i, page in enumerate(doc):
        text = page.get_text()
        if any(keyword in text for keyword in ['Inventory Calculation', 'Inventory Risk', 'service', 'workflow', 'replenishment', 'agent']):
            print('--- page', i+1, '---')
            for line in text.splitlines():
                if any(tok in line for tok in ['Inventory Calculation', 'Inventory Risk', 'service', 'workflow', 'replenishment', 'agent']):
                    print(line)
    doc.close()
