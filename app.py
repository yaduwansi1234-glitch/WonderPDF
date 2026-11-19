import os, io, tempfile, zipfile
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader, PdfWriter
from PIL import Image
import fitz
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from docx import Document
from pdf2docx import Converter

APP_DIR = Path(__file__).parent
app = FastAPI(title="WonderPDF")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

def stream(data: bytes, filename: str, media="application/pdf"):
    return StreamingResponse(io.BytesIO(data), media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

async def read_upload(upload):
    data = await upload.read()
    if not data:
        raise HTTPException(400, "Empty file")
    return data

@app.get("/", response_class=HTMLResponse)
def home():
    return (APP_DIR / "static" / "index.html").read_text(encoding="utf-8")

@app.post("/api/create-pdf")
async def create_pdf(text: str = Form(...)):
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=A4)
    width, height = A4
    y = height - 55
    for line in text.splitlines() or [""]:
        if y < 55:
            c.showPage(); y = height - 55
        c.setFont("Helvetica", 11)
        c.drawString(50, y, line.encode("latin-1", "replace").decode("latin-1")[:110])
        y -= 17
    c.save()
    return stream(out.getvalue(), "wonderpdf-document.pdf")

@app.post("/api/merge")
async def merge(files: list[UploadFile] = File(...)):
    if len(files) < 2: raise HTTPException(400, "Upload at least two PDFs")
    writer = PdfWriter()
    for f in files:
        reader = PdfReader(io.BytesIO(await read_upload(f)))
        if reader.is_encrypted: raise HTTPException(400, f"{f.filename} is password protected")
        for page in reader.pages: writer.add_page(page)
    out = io.BytesIO(); writer.write(out)
    return stream(out.getvalue(), "merged.pdf")

@app.post("/api/split")
async def split(file: UploadFile = File(...), pages: str = Form(...)):
    reader = PdfReader(io.BytesIO(await read_upload(file)))
    if reader.is_encrypted: raise HTTPException(400, "Unlock the PDF first")
    writer = PdfWriter()
    # Pages format: 1,3-5
    chosen = set()
    try:
        for part in pages.split(","):
            if "-" in part:
                a,b = map(int, part.split("-",1)); chosen.update(range(a,b+1))
            else: chosen.add(int(part))
        for n in sorted(chosen):
            if n < 1 or n > len(reader.pages): raise ValueError()
            writer.add_page(reader.pages[n-1])
    except Exception: raise HTTPException(400, "Invalid page selection. Example: 1,3-5")
    out=io.BytesIO(); writer.write(out)
    return stream(out.getvalue(), "split-pages.pdf")

@app.post("/api/compress")
async def compress(file: UploadFile = File(...)):
    doc = fitz.open(stream=await read_upload(file), filetype="pdf")
    out = doc.tobytes(garbage=4, deflate=True, clean=True)
    doc.close()
    return stream(out, "compressed.pdf")

@app.post("/api/pdf-to-word")
async def pdf_to_word(file: UploadFile = File(...)):
    src = await read_upload(file)
    with tempfile.TemporaryDirectory() as td:
        p=Path(td); inp=p/"in.pdf"; out=p/"out.docx"; inp.write_bytes(src)
        cv=Converter(str(inp)); cv.convert(str(out)); cv.close()
        return stream(out.read_bytes(), "converted.docx",
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

@app.post("/api/word-to-pdf")
async def word_to_pdf(file: UploadFile = File(...)):
    data=await read_upload(file)
    with tempfile.TemporaryDirectory() as td:
        p=Path(td); inp=p/(Path(file.filename or "file.docx").name); inp.write_bytes(data)
        import subprocess
        try:
            subprocess.run(["libreoffice","--headless","--convert-to","pdf","--outdir",td,str(inp)],
                           check=True, capture_output=True, timeout=90)
        except Exception:
            raise HTTPException(501, "Word-to-PDF needs LibreOffice installed on the server.")
        out=inp.with_suffix(".pdf")
        if not out.exists(): raise HTTPException(500, "Conversion failed")
        return stream(out.read_bytes(), "converted.pdf")

@app.post("/api/images-to-pdf")
async def images_to_pdf(files: list[UploadFile] = File(...)):
    imgs=[]
    for f in files:
        im=Image.open(io.BytesIO(await read_upload(f))).convert("RGB")
        imgs.append(im)
    if not imgs: raise HTTPException(400, "Upload images")
    out=io.BytesIO(); imgs[0].save(out, format="PDF", save_all=True, append_images=imgs[1:])
    return stream(out.getvalue(), "images.pdf")

@app.post("/api/extract-images")
async def extract_images(file: UploadFile = File(...)):
    doc=fitz.open(stream=await read_upload(file), filetype="pdf")
    mem=io.BytesIO()
    with zipfile.ZipFile(mem,"w",zipfile.ZIP_DEFLATED) as z:
        count=0
        for page_no,page in enumerate(doc,1):
            for img_no,img in enumerate(page.get_images(full=True),1):
                xref=img[0]; pix=fitz.Pixmap(doc,xref)
                if pix.n - pix.alpha > 3: pix=fitz.Pixmap(fitz.csRGB,pix)
                ext="png"; z.writestr(f"page-{page_no}-image-{img_no}.{ext}",pix.tobytes("png")); count+=1
        if count==0: z.writestr("README.txt","No embedded images found.")
    doc.close(); mem.seek(0)
    return StreamingResponse(mem,media_type="application/zip",
        headers={"Content-Disposition":'attachment; filename="extracted-images.zip"'})

@app.post("/api/protect")
async def protect(file: UploadFile = File(...), password: str = Form(...)):
    if len(password)<4: raise HTTPException(400,"Use at least 4 characters")
    reader=PdfReader(io.BytesIO(await read_upload(file)))
    writer=PdfWriter()
    for page in reader.pages: writer.add_page(page)
    writer.encrypt(password)
    out=io.BytesIO(); writer.write(out)
    return stream(out.getvalue(),"protected.pdf")

@app.post("/api/unlock")
async def unlock(file: UploadFile = File(...), password: str = Form(...)):
    reader=PdfReader(io.BytesIO(await read_upload(file)))
    if reader.is_encrypted and not reader.decrypt(password):
        raise HTTPException(401,"Incorrect password")
    writer=PdfWriter()
    for page in reader.pages: writer.add_page(page)
    out=io.BytesIO(); writer.write(out)
    return stream(out.getvalue(),"unlocked.pdf")

@app.post("/api/sign")
async def sign(file: UploadFile = File(...), signature: UploadFile = File(...),
               page: int = Form(1), x: float = Form(60), y: float = Form(60), width: float = Form(150)):
    pdf=fitz.open(stream=await read_upload(file),filetype="pdf")
    if page<1 or page>len(pdf): raise HTTPException(400,"Page number out of range")
    sig=await read_upload(signature)
    pg=pdf[page-1]; rect=fitz.Rect(x,y,x+width,y+width*0.45)
    pg.insert_image(rect,stream=sig,keep_proportion=True,overlay=True)
    out=pdf.tobytes(garbage=3,deflate=True); pdf.close()
    return stream(out,"signed.pdf")

@app.post("/api/edit")
async def edit(file: UploadFile = File(...), text: str = Form(...),
               page: int = Form(1), x: float = Form(60), y: float = Form(60)):
    doc=fitz.open(stream=await read_upload(file),filetype="pdf")
    if page<1 or page>len(doc): raise HTTPException(400,"Page number out of range")
    doc[page-1].insert_text((x,y),text,fontsize=12,color=(0.05,0.15,0.45),overlay=True)
    out=doc.tobytes(garbage=3,deflate=True); doc.close()
    return stream(out,"edited.pdf")
