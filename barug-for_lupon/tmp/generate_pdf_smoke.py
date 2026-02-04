import sys, os
# add project root so src package is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.infra.utilities.pdf_generator import PdfGenerator

out = '/workspaces/codespace/barug/tmp/test_smoke.pdf'

try:
    gen = PdfGenerator()
    pdf = gen.generate(
        title='Smoke Test PDF',
        header_lines=[('Test Header', 14), ('Sub', 10)],
        header_color='#003366',
        sections=[{'heading':'Section A', 'content':'This is a smoke test.'}],
    )
    with open(out, 'wb') as f:
        f.write(pdf)
    print('WROTE', out, os.path.getsize(out))
except Exception as e:
    import traceback
    traceback.print_exc()
    print('ERROR', str(e))
