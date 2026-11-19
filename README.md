# WonderPDF

Responsive PDF web app with installable PWA support for Android. The same app runs in a mobile browser and can be installed to the Android home screen.

## Features
- Create PDF from text
- PDF to Word (DOCX)
- Word to PDF (requires LibreOffice on the server)
- Merge and split PDFs
- Compress/optimize PDFs
- Extract embedded images to ZIP
- Convert images to PDF
- Add password / remove password with the correct password
- Add a signature image to a PDF page
- Add text overlays to a PDF page

## Run locally
Requires Python 3.10+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```
Open http://127.0.0.1:8000

For Word-to-PDF install LibreOffice on the server and ensure `libreoffice` is on PATH.

## Android
Deploy this app over HTTPS, open the URL in Chrome on Android, then choose **Install app** / **Add to Home screen**. This is an installable PWA, not a signed APK. A native APK would require a separate Android Studio wrapper/build.

## Important limitations and security
- PDF editing adds text overlays; it does not rewrite arbitrary existing PDF text or layouts.
- PDF signing places a signature image. It is not a certificate-based cryptographic digital signature.
- Password removal works only when the user supplies the correct password and has permission to unlock the file.
- PDF-to-Word layout fidelity varies by source PDF.
- Files are processed by the server. Add authentication, HTTPS, rate limits, upload-size limits, temporary-file cleanup, malware scanning and a privacy policy before public production deployment. Do not expose an unauthenticated public instance for confidential documents.
- The text-to-PDF generator currently uses a basic Latin font; extend it with a Unicode font for Hindi and other scripts.
