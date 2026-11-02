import unittest
from unittest.mock import patch
from paperman.corpus.validation import validate

DOI = "10.1007/test"
TEXT = "Measured polymer properties and experimental results. " * 12
DTD = '<!DOCTYPE response [<!ENTITY % article SYSTEM "https://invalid.example/jats.dtd">%article;<!ENTITY % book SYSTEM "file:///never-read.dtd">%book;]>'
ARTICLE = f'<response><article><article-id pub-id-type="doi">{DOI}</article-id><body><p>{TEXT}</p></body></article></response>'


class XMLValidationTest(unittest.TestCase):
    def test_external_parameter_dtds_accepted_without_io(self):
        with patch("builtins.open", side_effect=AssertionError("file access")), patch("socket.socket", side_effect=AssertionError("network access")):
            for encoding in ("utf-8", "utf-16"):
                self.assertTrue(validate((DTD + ARTICLE).encode(encoding), "xml", DOI)[0])

    def test_internal_and_general_entities_rejected(self):
        for declaration in ("<!ENTITY x 'expanded'>", '<!ENTITY x SYSTEM "file:///etc/passwd">', "<!ENTITY % x 'expanded'>"):
            for encoding in ("utf-8", "utf-16"):
                data = ('<!DOCTYPE response [' + declaration + ']>' + ARTICLE).encode(encoding)
                self.assertFalse(validate(data, "xml", DOI)[0])

    def test_bits_fulltext_and_identity(self):
        chapter = ARTICLE.replace('article-id', 'book-part-id').replace('pub-id-type', 'book-part-id-type').replace('<article>', '<book-part>').replace('</article>', '</book-part>').replace('<body>', '<book-part-body>').replace('</body>', '</book-part-body>')
        self.assertTrue(validate((DTD + chapter).encode(), "xml", DOI)[0])
        self.assertFalse(validate((DTD + chapter).encode(), "xml", "10.1007/wrong")[0])

    def test_missing_body_and_malformed_and_undefined_entity(self):
        for data in ('<response/>', '<response>', ARTICLE.replace(TEXT, '&unknown;'), ARTICLE.replace(TEXT, 'Abstract only')):
            self.assertFalse(validate((DTD + data).encode(), "xml", DOI)[0])


if __name__ == "__main__":
    unittest.main()
