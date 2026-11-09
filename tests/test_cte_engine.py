"""Testes do motor. Execute com: python -m unittest discover -s tests"""

import sys
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cte_engine as engine  # noqa: E402


def make_key(number: int, model: str = "57", series: int = 3, branch: str = "0001") -> str:
    base = f"3526111122233300{branch}{model}{series:03d}{number:09d}1{12345678:08d}"[:43]
    return base + str(engine.key_check_digit(base))


def spaced(key: str) -> str:
    return " ".join(key[i:i + 4] for i in range(0, 44, 4))


def page_text(key=None, number=None, sheet="1 / 1", extra=""):
    parts = ["DACTE"]
    if number is not None:
        parts.append(f" NÚMERO\n{number}")
    if key:
        parts.append(f" CHA VE DE ACESSO\n{spaced(key)}")
    parts.append(extra)
    if sheet:
        parts.append(sheet)
    return "\n".join(parts)


class KeyTests(unittest.TestCase):
    def test_known_key_is_valid(self):
        key = "35261111222333000181570030000007741123456789"  # CNPJ fictício
        self.assertTrue(engine.is_valid_key(key))
        self.assertEqual(engine.number_from_key(key), "774")
        self.assertEqual(engine.series_from_key(key), "3")

    def test_changed_digit_is_invalid(self):
        self.assertFalse(engine.is_valid_key("35261111222333000181570030000007741123456780"))


class ParsingTests(unittest.TestCase):
    def test_nfe_key_is_not_taken_as_cte_key(self):
        nfe = make_key(555, model="55")
        self.assertIsNone(engine.parse_page_text(f"NFe 003/555  {nfe}").key)

    def test_header_key_wins_over_referenced_cte_key(self):
        own, referenced = make_key(10), make_key(99)
        text = f"DOCUMENTOS\nCTe {referenced}\n" + page_text(own, 10)
        self.assertEqual(engine.parse_page_text(text).key, own)

    def test_sheet_indicator_uses_last_standalone_line(self):
        info = engine.parse_page_text(page_text(make_key(1), 1, sheet="2 / 3"))
        self.assertEqual((info.sheet, info.sheet_total), (2, 3))

    def test_page_without_cte_data_is_unidentified(self):
        self.assertFalse(engine.parse_page_text("Página em branco").identified)


class GroupingTests(unittest.TestCase):
    def group(self, *texts):
        return engine.group_pages([engine.parse_page_text(text) for text in texts])

    def test_multi_sheet_cte_becomes_one_document(self):
        key = make_key(132570)
        docs, unidentified = self.group(
            page_text(key, 132570, "1 / 2"), page_text(key, 132570, "2 / 2")
        )
        self.assertEqual([d.pages for d in docs], [[0, 1]])
        self.assertEqual(unidentified, [])
        self.assertFalse(docs[0].needs_review)

    def test_out_of_order_sheets_are_reordered(self):
        key = make_key(7)
        docs, _ = self.group(page_text(key, 7, "2 / 2"), page_text(key, 7, "1 / 2"))
        self.assertEqual(docs[0].pages, [1, 0])

    def test_duplicated_sheet_keeps_first_copy_and_warns(self):
        key = make_key(8)
        docs, _ = self.group(page_text(key, 8), page_text(key, 8))
        self.assertEqual(docs[0].pages, [0])
        self.assertTrue(docs[0].needs_review)

    def test_missing_sheet_warns(self):
        docs, _ = self.group(page_text(make_key(9), 9, "1 / 2"))
        self.assertTrue(docs[0].needs_review)

    def test_number_mismatch_warns(self):
        docs, _ = self.group(page_text(make_key(10), 11))
        self.assertEqual(docs[0].number, "10")
        self.assertTrue(docs[0].needs_review)

    def test_page_with_only_printed_number_is_kept_and_flagged(self):
        docs, _ = self.group(page_text(None, "00042"))
        self.assertEqual(docs[0].number, "42")
        self.assertTrue(docs[0].needs_review)

    def test_blank_page_is_reported(self):
        docs, unidentified = self.group(page_text(make_key(1), 1), "")
        self.assertEqual(len(docs), 1)
        self.assertEqual(unidentified, [1])


class NamingTests(unittest.TestCase):
    def test_same_number_from_other_branch_gets_suffix(self):
        docs = [
            engine.CteDocument("774", key="a"),
            engine.CteDocument("775", key="b"),
            engine.CteDocument("774", key="c"),
        ]
        self.assertEqual(
            engine.plan_filenames(docs, "CTE_"), ["CTE_774.pdf", "CTE_775.pdf", "CTE_774_2.pdf"]
        )
        engine.mark_repeated_numbers(docs)
        self.assertEqual([d.needs_review for d in docs], [True, False, True])

    def test_prefix_cannot_escape_output_folder(self):
        docs = [engine.CteDocument("1")]
        self.assertEqual(engine.plan_filenames(docs, '..\\a/b:"'), ["..ab1.pdf"])


class ExportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.source = self.dir / "origem.pdf"
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(100, 100)
        with self.source.open("wb") as stream:
            writer.write(stream)
        self.result = engine.AnalysisResult(
            self.source, 3, [engine.CteDocument("1", pages=[0, 1])], [2]
        )
        self.out = self.dir / "saida"

    def tearDown(self):
        self._tmp.cleanup()

    def test_export_preserves_every_page(self):
        items = engine.export_documents(self.result, self.out)
        self.assertTrue(all(item.error is None for item in items))
        self.assertTrue((self.out / "1.pdf").exists())
        self.assertTrue((self.out / f"{engine.UNIDENTIFIED_STEM}.pdf").exists())
        self.assertEqual(list(self.out.glob("*.part")), [])

    def test_keep_both_does_not_touch_existing_file(self):
        self.out.mkdir()
        existing = self.out / "1.pdf"
        existing.write_bytes(b"antigo")
        items = engine.export_documents(self.result, self.out)
        self.assertEqual(existing.read_bytes(), b"antigo")
        self.assertEqual(items[0].path.name, "1_2.pdf")

    def test_replace_overwrites_existing_file(self):
        self.out.mkdir()
        existing = self.out / "1.pdf"
        existing.write_bytes(b"antigo")
        engine.export_documents(self.result, self.out, on_conflict=engine.ON_CONFLICT_REPLACE)
        self.assertNotEqual(existing.read_bytes(), b"antigo")

    def test_source_is_never_overwritten(self):
        source = self.dir / "1.pdf"
        source.write_bytes(self.source.read_bytes())
        original = source.read_bytes()
        result = engine.AnalysisResult(source, 3, [engine.CteDocument("1", pages=[0])], [])
        items = engine.export_documents(result, self.dir, on_conflict=engine.ON_CONFLICT_REPLACE)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(items[0].path.name, "1_2.pdf")

    def test_corrupt_file_raises_friendly_error(self):
        bad = self.dir / "ruim.pdf"
        bad.write_bytes(b"isto nao e um pdf")
        with self.assertRaises(engine.PdfAnalysisError):
            engine.analyze_pdf(bad)


if __name__ == "__main__":
    unittest.main()
