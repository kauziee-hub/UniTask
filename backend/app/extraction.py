"""Turn an uploaded document into per-page text.

Order of preference:
1. Native text (PDF text layer, DOCX/PPTX XML, plain text): exact and free.
2. Amazon Textract, for scans and photos, when OCR_PROVIDER=textract.
3. The configured vision model (Gemini/Bedrock), when OCR_PROVIDER=llm.
Pages that yield no text are reported as needing OCR rather than silently treated as empty.
"""

import io
import logging
import os
import re
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree

from . import llm

logger = logging.getLogger(__name__)
MIN_TEXT_CHARS = 25


@dataclass
class Extracted:
    pages: list[str] = field(default_factory=list)
    extractor: str = "none"
    needs_ocr: bool = False
    error: str | None = None


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _pdf(content: bytes) -> Extracted:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [_clean(page.extract_text() or "") for page in reader.pages]
    except (PdfReadError, ValueError, KeyError) as exc:
        return Extracted(extractor="pdf", error=f"Could not read this PDF: {exc}")
    readable = sum(1 for page in pages if len(page) >= MIN_TEXT_CHARS)
    return Extracted(pages=pages, extractor="pdf", needs_ocr=bool(pages) and readable < max(1, len(pages) // 3))


def _office(content: bytes, kind: str) -> Extracted:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        return Extracted(extractor=kind, error="This file is not a valid Office document.")

    def text_of(name: str) -> str:
        root = ElementTree.fromstring(archive.read(name))
        paragraphs = []
        for para in root.iter():
            if para.tag.endswith("}p"):
                words = "".join(node.text or "" for node in para.iter() if node.tag.endswith("}t"))
                if words.strip():
                    paragraphs.append(words)
        return _clean("\n".join(paragraphs))

    if kind == "docx":
        return Extracted(pages=[text_of("word/document.xml")], extractor="docx")
    slides = sorted(
        (n for n in archive.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
        key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)),
    )
    return Extracted(pages=[text_of(name) for name in slides], extractor="pptx")


def _textract(content: bytes) -> Extracted:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    profile = os.getenv("AWS_PROFILE") or None
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    client = session.client("textract", region_name=os.getenv("TEXTRACT_REGION") or os.getenv("AWS_REGION", "ap-south-1"))
    try:
        response = client.detect_document_text(Document={"Bytes": content})
    except (BotoCoreError, ClientError) as exc:
        logger.warning("Textract failed: %s", exc)
        return Extracted(extractor="textract", error="Amazon Textract could not read this file.")
    lines = [block["Text"] for block in response.get("Blocks", []) if block.get("BlockType") == "LINE"]
    return Extracted(pages=[_clean("\n".join(lines))], extractor="textract")


def _vision(content: bytes, mime: str) -> Extracted:
    try:
        text = llm.generate(
            "You transcribe academic documents. Return only the text you can see, in reading order, "
            "preserving question numbers, headings and marks. Do not add anything that is not visible.",
            "Transcribe this page.",
            fast=True,
            image=(content, mime),
        )
    except llm.LLMError as exc:
        return Extracted(extractor="vision", error=str(exc), needs_ocr=True)
    return Extracted(pages=[_clean(text)], extractor="vision")


def ocr(content: bytes, mime: str) -> Extracted:
    provider = os.getenv("OCR_PROVIDER", "llm" if llm.available() else "none").lower()
    if provider == "textract":
        return _textract(content)
    if provider == "llm" and llm.available():
        return _vision(content, mime)
    return Extracted(extractor="none", needs_ocr=True, error="No OCR provider is configured for scanned pages.")


def extract(content: bytes, content_type: str, filename: str) -> Extracted:
    name = filename.lower()
    if content_type == "application/pdf":
        result = _pdf(content)
        if result.needs_ocr and os.getenv("OCR_PROVIDER", "").lower() == "textract" and len(result.pages) == 1:
            return _textract(content)  # synchronous Textract handles single-page PDFs
        return result
    if name.endswith(".docx"):
        return _office(content, "docx")
    if name.endswith(".pptx"):
        return _office(content, "pptx")
    if content_type.startswith("image/"):
        return ocr(content, content_type)
    if content_type.startswith("text/") or name.endswith((".md", ".csv", ".ipynb", ".py", ".sql")):
        text = content.decode("utf-8", errors="replace")
        # Split long text files into ~3000-character "pages" so citations stay specific.
        chunks = [text[i : i + 3000] for i in range(0, len(text), 3000)] or [""]
        return Extracted(pages=[_clean(chunk) for chunk in chunks], extractor="text")
    return Extracted(extractor="none", error="UniTask can't read text from this file type.")
