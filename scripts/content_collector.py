#!/usr/bin/env python3
"""
to-study — Content Collector (Extended)
Extends collect-study's ContentCollector with additional source formats.

Dependencies: requests, beautifulsoup4, PyMuPDF, python-docx, ebooklib, lxml
"""

import os
import re
import json
import hashlib
import tempfile
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# --- Optional imports with graceful fallback ---
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    import ebooklib
    from ebooklib import epub
    HAS_EBOOKLIB = True
except ImportError:
    HAS_EBOOKLIB = False


@dataclass
class CollectedContent:
    """Structured result from content collection."""
    source: str                          # URL or file path
    source_type: str                     # url / pdf / docx / epub / md / txt / html
    title: str = ""
    content: str = ""                     # Full extracted text
    metadata: Dict = field(default_factory=dict)
    encoding: str = "utf-8"
    word_count: int = 0
    needs_playwright: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class ContentCollector:
    """
    Multi-source content collector.
    Handles URLs (static), PDFs, Word documents, EPUBs, Markdown, HTML, and plain text.
    """

    ENCODING_CANDIDATES = ["utf-8", "gbk", "gb2312", "gb18030", "utf-16", "latin-1"]
    SPA_SIGNALS = [
        ('div', {'id': 'app'}),
        ('div', {'id': 'root'}),
        ('div', {'class_': re.compile(r'app|root|main', re.I)}),
    ]

    def __init__(self, timeout: int = 30, user_agent: str = None):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

    # ── Public API ─────────────────────────────────────────

    def collect(self, source: str, source_type: str = "auto") -> CollectedContent:
        """
        Main entry point. Auto-detects source_type if set to 'auto'.
        """
        if source_type == "auto":
            source_type = self._detect_source_type(source)

        handlers = {
            "url": self._collect_from_url,
            "pdf": self._collect_from_pdf,
            "docx": self._collect_from_docx,
            "epub": self._collect_from_epub,
            "md": self._collect_from_markdown,
            "txt": self._collect_from_text,
            "html": self._collect_from_html_file,
        }

        handler = handlers.get(source_type)
        if handler is None:
            return CollectedContent(
                source=source, source_type=source_type,
                error=f"Unsupported source type: {source_type}"
            )

        try:
            result = handler(source)
            if result.error is None:
                result.word_count = len(result.content)
            return result
        except Exception as e:
            return CollectedContent(
                source=source, source_type=source_type,
                error=f"{type(e).__name__}: {e}"
            )

    def collect_and_save(self, source: str, output_dir: str,
                         source_type: str = "auto") -> CollectedContent:
        """Collect content and save to output directory."""
        result = self.collect(source, source_type)
        if result.error:
            return result

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        safe_name = self._safe_filename(result.title or "content")
        content_file = out_path / f"{safe_name}.md"

        content_file.write_text(f"# {result.title}\n\n{result.content}", encoding="utf-8")

        meta_file = out_path / f"{safe_name}_meta.json"
        meta_file.write_text(result.to_json(), encoding="utf-8")

        return result

    # ── Source Detection ───────────────────────────────────

    def _detect_source_type(self, source: str) -> str:
        """Auto-detect source type from path/URL extension."""
        ext = Path(source).suffix.lower()
        if ext in (".pdf",):
            return "pdf"
        if ext in (".docx", ".doc"):
            return "docx"
        if ext in (".epub",):
            return "epub"
        if ext in (".md", ".markdown"):
            return "md"
        if ext in (".txt", ".text"):
            return "txt"
        if ext in (".html", ".htm"):
            return "html"
        if source.startswith(("http://", "https://")):
            return "url"
        # Fallback: try as text
        return "txt"

    # ── URL Collection ─────────────────────────────────────

    def _collect_from_url(self, url: str) -> CollectedContent:
        """Collect content from a static web page."""
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()

        # Detect encoding from response or content
        encoding = self._detect_html_encoding(resp)
        html = resp.content.decode(encoding, errors="replace")

        # Check if page needs Playwright
        if self._is_dynamic_page(html):
            return CollectedContent(
                source=url, source_type="url",
                needs_playwright=True,
                title=self._extract_title(html),
                error="Dynamic page detected — use playwright_fetcher.py"
            )

        soup = BeautifulSoup(html, "lxml")
        title = self._extract_title_from_soup(soup)
        content = self._extract_body(soup)

        return CollectedContent(
            source=url, source_type="url",
            title=title, content=content,
            encoding=encoding,
            metadata={"url": url, "status_code": resp.status_code}
        )

    def _is_dynamic_page(self, html: str) -> bool:
        """Heuristic check for SPA / JS-rendered pages."""
        soup = BeautifulSoup(html, "lxml")
        body = soup.find("body")
        if body is None:
            return True
        body_text = body.get_text(strip=True)

        # SPA mount points
        for tag, attrs in self.SPA_SIGNALS:
            if soup.find(tag, attrs):
                return True

        # High script-to-content ratio
        scripts = len(soup.find_all("script"))
        text_len = len(body_text)
        if scripts > 5 and text_len < 500:
            return True

        # Empty-ish body
        if text_len < 200:
            return True

        return False

    def _extract_title_from_soup(self, soup: BeautifulSoup) -> str:
        """Extract title from BeautifulSoup document."""
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        return "Untitled"

    def _extract_title(self, html: str) -> str:
        """Extract title from raw HTML string."""
        soup = BeautifulSoup(html, "lxml")
        return self._extract_title_from_soup(soup)

    def _extract_body(self, soup: BeautifulSoup) -> str:
        """Extract readable body content from BeautifulSoup document."""
        # Remove non-content elements
        for tag in soup.find_all(["script", "style", "nav", "footer", "header",
                                   "noscript", "iframe", "form"]):
            tag.decompose()

        # Try semantic containers first
        for selector in ["article", "main", '[role="main"]',
                         ".content", ".post-body", ".article-content",
                         "#content", "#article", ".markdown-body"]:
            container = soup.select_one(selector)
            if container:
                return self._clean_text(container.get_text("\n", strip=True))

        body = soup.find("body")
        if body:
            return self._clean_text(body.get_text("\n", strip=True))

        return self._clean_text(soup.get_text("\n", strip=True))

    # ── PDF Collection ─────────────────────────────────────

    def _collect_from_pdf(self, path: str) -> CollectedContent:
        """Extract text from PDF using PyMuPDF."""
        if not HAS_PYMUPDF:
            return CollectedContent(
                source=path, source_type="pdf",
                error="PyMuPDF not installed. Run: pip install PyMuPDF"
            )

        doc = fitz.open(path)
        title = doc.metadata.get("title", "") or Path(path).stem
        pages = []
        for page in doc:
            pages.append(page.get_text("text"))
        doc.close()

        content = "\n\n".join(pages)
        return CollectedContent(
            source=path, source_type="pdf",
            title=title, content=content,
            metadata={
                "file": path,
                "pages": len(pages),
                "pdf_title": doc.metadata.get("title", ""),
                "author": doc.metadata.get("author", ""),
            }
        )

    # ── Word Collection ────────────────────────────────────

    def _collect_from_docx(self, path: str) -> CollectedContent:
        """Extract text from Word document."""
        if not HAS_DOCX:
            return CollectedContent(
                source=path, source_type="docx",
                error="python-docx not installed. Run: pip install python-docx"
            )

        doc = Document(path)
        title = ""
        paragraphs = []

        for i, para in enumerate(doc.paragraphs):
            text = para.text.strip()
            if not text:
                paragraphs.append("")
                continue
            # Use first non-empty paragraph as title if no explicit title
            if not title and i < 3:
                title = text
                paragraphs.append(f"# {text}")
            else:
                paragraphs.append(text)

        content = "\n\n".join(paragraphs)
        return CollectedContent(
            source=path, source_type="docx",
            title=title or Path(path).stem,
            content=content,
            metadata={"file": path}
        )

    # ── EPUB Collection ────────────────────────────────────

    def _collect_from_epub(self, path: str) -> CollectedContent:
        """Extract text from EPUB."""
        if not HAS_EBOOKLIB:
            return CollectedContent(
                source=path, source_type="epub",
                error="ebooklib not installed. Run: pip install ebooklib"
            )

        book = epub.read_epub(path)
        title = book.get_metadata("DC", "title")
        title = title[0][0] if title else Path(path).stem

        chapters = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_content(), "html.parser")
            text = soup.get_text("\n", strip=True)
            if text:
                chapters.append(text)

        content = "\n\n---\n\n".join(chapters)
        return CollectedContent(
            source=path, source_type="epub",
            title=title, content=content,
            metadata={
                "file": path,
                "chapters": len(chapters),
                "title": title,
            }
        )

    # ── Markdown / Text / HTML File Collection ─────────────

    def _collect_from_markdown(self, path: str) -> CollectedContent:
        """Read Markdown file."""
        raw = self._read_file_with_encoding(path)
        title = self._extract_md_title(raw)
        return CollectedContent(
            source=path, source_type="md",
            title=title or Path(path).stem,
            content=raw,
            encoding=self._last_detected_encoding,
            metadata={"file": path}
        )

    def _collect_from_text(self, path: str) -> CollectedContent:
        """Read plain text file."""
        raw = self._read_file_with_encoding(path)
        return CollectedContent(
            source=path, source_type="txt",
            title=Path(path).stem,
            content=raw,
            encoding=self._last_detected_encoding,
            metadata={"file": path}
        )

    def _collect_from_html_file(self, path: str) -> CollectedContent:
        """Read local HTML file and extract body."""
        raw = self._read_file_with_encoding(path)
        soup = BeautifulSoup(raw, "lxml")
        title = self._extract_title_from_soup(soup)
        content = self._extract_body(soup)
        return CollectedContent(
            source=path, source_type="html",
            title=title or Path(path).stem,
            content=content,
            encoding=self._last_detected_encoding,
            metadata={"file": path}
        )

    # ── Helpers ────────────────────────────────────────────

    _last_detected_encoding = "utf-8"

    def _read_file_with_encoding(self, path: str) -> str:
        """Read file with automatic encoding detection."""
        raw_bytes = Path(path).read_bytes()

        # Try UTF-8 BOM first
        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            self._last_detected_encoding = "utf-8-sig"
            return raw_bytes.decode("utf-8-sig", errors="replace")

        # Try UTF-16 BOM
        if raw_bytes.startswith(b"\xff\xfe"):
            self._last_detected_encoding = "utf-16-le"
            return raw_bytes.decode("utf-16-le", errors="replace")
        if raw_bytes.startswith(b"\xfe\xff"):
            self._last_detected_encoding = "utf-16-be"
            return raw_bytes.decode("utf-16-be", errors="replace")

        # Try candidate encodings
        for enc in self.ENCODING_CANDIDATES:
            try:
                text = raw_bytes.decode(enc)
                self._last_detected_encoding = enc
                return text
            except (UnicodeDecodeError, LookupError):
                continue

        # Fallback
        self._last_detected_encoding = "latin-1"
        return raw_bytes.decode("latin-1", errors="replace")

    def _extract_md_title(self, text: str) -> str:
        """Extract title from Markdown (# heading)."""
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("# ") and not line.startswith("## "):
                return line[2:].strip()
        return ""

    @staticmethod
    def _detect_html_encoding(response) -> str:
        """Detect encoding from HTTP response or HTML meta tags."""
        if response.encoding and response.encoding.lower() != "iso-8859-1":
            return response.encoding
        # Check meta charset
        match = re.search(
            rb'<meta[^>]+charset=["\']?([a-zA-Z0-9\-_]+)',
            response.content[:2048], re.I
        )
        if match:
            return match.group(1).decode("ascii").lower()
        return "utf-8"

    @staticmethod
    def _clean_text(text: str) -> str:
        """Clean extracted text: normalize whitespace and blank lines."""
        lines = []
        prev_empty = False
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                if not prev_empty:
                    lines.append("")
                    prev_empty = True
            else:
                lines.append(stripped)
                prev_empty = False
        return "\n".join(lines)

    @staticmethod
    def _safe_filename(name: str) -> str:
        """Sanitize a string for use as a filename."""
        name = re.sub(r'[<>:"/\\|?*]', "_", name)
        name = name.strip().rstrip(".")
        return name[:100] if name else "content"


# ── CLI ────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="to-study Content Collector")
    parser.add_argument("source", help="URL or file path to collect")
    parser.add_argument("-t", "--type", default="auto",
                        choices=["auto", "url", "pdf", "docx", "epub", "md", "txt", "html"],
                        help="Source type (default: auto-detect)")
    parser.add_argument("-o", "--output", default=None,
                        help="Output directory to save results")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    args = parser.parse_args()

    collector = ContentCollector()

    if args.output:
        result = collector.collect_and_save(args.source, args.output, args.type)
    else:
        result = collector.collect(args.source, args.type)

    if args.json:
        print(result.to_json())
    else:
        if result.error:
            print(f"ERROR: {result.error}")
            if result.needs_playwright:
                print("Hint: Use playwright_fetcher.py for dynamic pages")
        else:
            print(f"Title: {result.title}")
            print(f"Source: {result.source}")
            print(f"Type: {result.source_type}")
            print(f"Encoding: {result.encoding}")
            print(f"Words: {result.word_count}")
            print(f"\n--- Content Preview (first 500 chars) ---")
            print(result.content[:500])