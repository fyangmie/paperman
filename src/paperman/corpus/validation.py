from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.parsers import expat
from html.parser import HTMLParser


class ArticleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.paragraphs = []
        self.current = None
        self.article_markers = False
        self.metadata = {}
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        marker = " ".join(attrs.get(key, "") for key in (
            "id", "class", "itemprop", "data-title", "aria-label", "aria-labelledby")).lower()
        body_marker = any(s in marker for s in ("article-body", "article__body", "articlebody", "fulltext",
                                                "full-text", "article-section", "article-content", "article_content", "section-content"))
        normalized_marker = marker.replace("-", " ").replace("_", " ")
        excluded = any(s in normalized_marker for s in (
            "abstract", "reference", "bibliograph", "related content",
            "author information", "author contribution", "affiliation",
            "acknowledg", "funding", "rights and permissions", "copyright",
            "ethics declaration", "data availability", "supplementary information",
            "cite this article", "publisher note", "about this article",
        )) or tag in {"nav", "footer", "aside"}
        excluded = excluded or (self.stack[-1][2] if self.stack else False)
        active = (body_marker or (self.stack[-1][1] if self.stack else False)) and not excluded
        if body_marker:
            self.article_markers = True
        if tag == "meta":
            name = attrs.get("name", attrs.get("property", "")).lower()
            self.metadata[name] = attrs.get("content", "")
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append((tag, active, excluded))
        if tag == "p" and active:
            self.current = []

    def handle_endtag(self, tag):
        if tag == "p" and self.current is not None:
            text = " ".join(self.current)
            if len(text.strip()) >= 80:
                self.paragraphs.append(text)
            self.current = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                self.stack = self.stack[:i]
                break

    def handle_data(self, data):
        if not any(tag in {"script", "style", "noscript"} for tag, _, _ in self.stack):
            self.text.append(data)
            if self.current is not None:
                self.current.append(data)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


class UnsafeEntity(ValueError):
    pass


def parse_article_xml(body: bytes):
    """Allow publisher DTD references without resolving them or expanding entities."""
    parser = expat.ParserCreate()
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)

    def entity_decl(name, is_parameter, value, base, system_id, public_id, notation):
        # Springer declares external parameter entities for the JATS/BITS DTDs.
        # They are never fetched. Internal and general entity declarations remain forbidden.
        if not (is_parameter and system_id and value is None and notation is None):
            raise UnsafeEntity("XML entity declarations are disabled")

    parser.EntityDeclHandler = entity_decl
    parser.ExternalEntityRefHandler = lambda *args: 1  # Skip, never fetch external resources.
    parser.Parse(body, True)
    # ElementTree does not load external DTDs. The preflight rejected internal entities.
    return ET.fromstring(body)


def validate(body: bytes, fmt: str, doi: str, content_type: str = "") -> tuple[bool, str]:
    if not body.strip():
        return False, "Empty response"
    if b"%PDF" in body[:1024] or "application/pdf" in content_type.lower():
        return False, "PDF response"
    if fmt == "xml":
        try:
            root = parse_article_xml(body)
        except UnsafeEntity as exc:
            return False, str(exc)
        except (ET.ParseError, expat.ExpatError, ValueError):
            return False, "Malformed XML"
        if local(root.tag) not in {"article", "full-text-retrieval-response", "articles", "response", "document", "book-part-wrapper", "book-part"}:
            return False, "Not an article XML document"
        bodies = [node for node in root.iter() if local(node.tag) in {"body", "rawtext", "book-part-body"}]
        paragraphs = [node for body_node in bodies for node in body_node.iter()
                      if local(node.tag) in {"p", "para", "simple-para"}]
        if not bodies or not any(len(" ".join(node.itertext()).strip()) >= 300 for node in bodies):
            return False, "XML has no substantive full-text body"
        if not paragraphs and not any(local(node.tag) == "rawtext" for node in bodies):
            return False, "XML has no body paragraphs"
        identifiers = ["".join(node.itertext()).strip().lower() for node in root.iter()
                       if local(node.tag) in {"doi", "article-id", "book-part-id"} and
                       (local(node.tag) == "doi" or node.attrib.get("book-part-id-type" if local(node.tag) == "book-part-id" else "pub-id-type", "").lower() == "doi")]
        if identifiers and doi.lower() not in identifiers and "https://doi.org/" + doi.lower() not in identifiers:
            return False, "DOI mismatch"
        return True, "Full-text XML body validated; " + ("DOI verified" if identifiers else "manual identity check required")
    try:
        parser = ArticleHTML()
        parser.feed(body.decode("utf-8", errors="replace"))
    except (ValueError, AssertionError):
        return False, "Malformed HTML"
    text = " ".join(parser.text).lower()
    if any(s in text for s in ("verify you are human", "checking your browser", "just a moment...", "access denied")):
        return False, "Challenge or access-denied page"
    if "preview of subscription content" in text:
        return False, "Subscription preview; full article body unavailable"
    if not parser.article_markers or len(parser.paragraphs) < 2 or sum(map(len, parser.paragraphs)) < 500:
        return False, "No substantive article body (landing, abstract, or login page)"
    stated = parser.metadata.get("citation_doi", parser.metadata.get("dc.identifier", "")).lower()
    if stated.startswith("doi:"):
        stated = stated[4:].strip()
    if stated and stated not in {doi.lower(), "https://doi.org/" + doi.lower()}:
        return False, "DOI mismatch"
    return True, "Full-text HTML body validated; " + ("DOI verified" if stated else "manual identity check required")
