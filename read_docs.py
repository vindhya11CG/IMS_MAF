import fitz
import pathlib

files = [
    "Business Requirements Document.pdf",
    "Inventory_Management_System_Specification (1).pdf",
    "main_workflow_doc.pdf",
]
base = pathlib.Path("docs")

for f in files:
    path = base / f
    print("===", f, "===")
    doc = fitz.open(str(path))
    text = doc[0].get_text()
    print(text[:1200].replace("\n", " "))
    print("---")
    doc.close()
