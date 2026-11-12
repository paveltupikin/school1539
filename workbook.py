"""Минимальная выгрузка XLSX с безопасными текстовыми ячейками."""

from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


def xlsx(rows):
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package = "http://schemas.openxmlformats.org/package/2006/relationships"
    records = []
    for index, row in enumerate(rows, 1):
        cells = []
        for col, value in enumerate(row):
            cell = f"{chr(65 + col)}{index}"
            if type(value) is int:
                cells.append(f'<c r="{cell}"><v>{value}</v></c>')
            else:
                text = escape("".join(c for c in str(value) if ord(c) >= 32 or c in "\t\n\r"))
                cells.append(f'<c r="{cell}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>')
        records.append(f'<row r="{index}">{"".join(cells)}</row>')
    entries = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": f'<Relationships xmlns="{package}"><Relationship Id="rId1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets><sheet name="Результаты" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<Relationships xmlns="{package}"><Relationship Id="rId1" Type="{rel}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{main}"><sheetData>{"".join(records)}</sheetData></worksheet>',
    }
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for path, text in entries.items():
            archive.writestr(path, text.encode())
    return buffer.getvalue()
