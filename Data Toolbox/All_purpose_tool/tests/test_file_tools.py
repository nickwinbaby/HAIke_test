import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile
import zlib

from core.file_checksum import calculate_bytes_checksums, calculate_checksums, calculate_md5, collect_files
from core.file_compare import compare_files, compare_folders


def write_test_docx(path, paragraph_text, table_value):
    document_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>{paragraph_text}</w:t></w:r></w:p>
    <w:tbl><w:tr>
      <w:tc><w:p><w:r><w:t>项目</w:t></w:r></w:p></w:tc>
      <w:tc><w:p><w:r><w:t>{table_value}</w:t></w:r></w:p></w:tc>
    </w:tr></w:tbl>
    <w:sectPr/>
  </w:body>
</w:document>'''
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)


class Md5Tests(unittest.TestCase):
    def test_calculate_md5_and_collect_folder_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "a.txt"
            second = root / "sub" / "b.bin"
            second.parent.mkdir()
            first.write_bytes(b"abc")
            second.write_bytes(b"123")
            result = calculate_md5(first)
            self.assertEqual(result.md5, hashlib.md5(b"abc").hexdigest())
            self.assertEqual(result.size, 3)
            self.assertEqual(collect_files((root,)), [first.resolve(), second.resolve()])

    def test_calculate_selected_checksum_algorithms(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "data.bin"
            source.write_bytes(b"abc")
            result = calculate_checksums(source, ("md5", "sha1", "sha256", "crc32"))
            self.assertEqual(list(result.checksums), ["md5", "sha1", "sha256", "crc32"])
            self.assertEqual(result.md5, hashlib.md5(b"abc").hexdigest())
            self.assertEqual(result.sha1, hashlib.sha1(b"abc").hexdigest())
            self.assertEqual(result.sha256, hashlib.sha256(b"abc").hexdigest())
            self.assertEqual(result.crc32, "352441c2")

    def test_calculate_text_bytes_checksums(self):
        result = calculate_bytes_checksums(b"hello", ("md5", "sha256", "crc32"))
        self.assertEqual(result["md5"], "5d41402abc4b2a76b9719d911017c592")
        self.assertEqual(result["sha256"], "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")
        self.assertEqual(result["crc32"], "3610a686")

    def test_crc32_rl_normalizes_config_lines_in_text_and_files(self):
        canonical = b"A=1\n\nPATH=C:\\test\\file\nB=2\n"
        displayed = b"A=1\\\r\n\r\nPATH=C:\\test\\file\\\rB=2\\"
        algorithms = ("crc32", "crc32_rl")
        expected = {"crc32": f"{zlib.crc32(displayed):08x}", "crc32_rl": "A7256540"}
        self.assertEqual(calculate_bytes_checksums(displayed, algorithms), expected)
        self.assertEqual(calculate_bytes_checksums(canonical, ("crc32_rl",)), {"crc32_rl": "A7256540"})
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Path(temp_dir) / "settings.txt"
            config.write_bytes(displayed)
            for chunk_size in range(1, len(displayed) + 1):
                with self.subTest(chunk_size=chunk_size):
                    result = calculate_checksums(config, algorithms, chunk_size=chunk_size)
                    self.assertEqual(result.checksums, expected)

    def test_crc32_rl_preserves_the_selected_text_encoding(self):
        encoding = "UTF-16LE"
        data = "名称=测试\\\r\n".encode(encoding)
        canonical = "名称=测试\n".encode(encoding)
        result = calculate_bytes_checksums(data, ("crc32_rl",), text_encoding=encoding)
        self.assertEqual(result["crc32_rl"], f"{zlib.crc32(canonical):08X}")


class FileComparisonTests(unittest.TestCase):
    def test_compare_text_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            left = root / "left.txt"
            right = root / "right.txt"
            left.write_text("same\nold\n", encoding="utf-8")
            right.write_text("same\nnew\n", encoding="utf-8")
            result = compare_files(left, right, hide_same=True)
            self.assertFalse(result.identical)
            self.assertTrue(result.text_comparison)
            self.assertEqual(result.same_lines, 1)
            self.assertEqual(result.deleted_lines, 1)
            self.assertEqual(result.added_lines, 1)
            different = [row for row in result.rows if row.status == "different"]
            self.assertEqual(len(different), 1)
            self.assertEqual(different[0].left_text.rstrip("\r\n"), "old")
            self.assertEqual(different[0].right_text.rstrip("\r\n"), "new")

    def test_compare_folders_by_relative_path_and_attributes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            left = root / "left"
            right = root / "right"
            left.mkdir()
            right.mkdir()
            (left / "same.txt").write_text("same", encoding="utf-8")
            (right / "same.txt").write_text("same", encoding="utf-8")
            (left / "changed.txt").write_text("old", encoding="utf-8")
            (right / "changed.txt").write_text("new-value", encoding="utf-8")
            (left / "left.txt").write_text("left", encoding="utf-8")
            (right / "right.txt").write_text("right", encoding="utf-8")
            result = compare_folders(left, right)
            statuses = {entry.relative_path: entry.status for entry in result.entries}
            self.assertEqual(statuses, {
                "changed.txt": "different",
                "left.txt": "only_left",
                "right.txt": "only_right",
                "same.txt": "same",
            })

    def test_compare_folders_includes_empty_directories_and_type_conflicts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            left = root / "left"
            right = root / "right"
            left.mkdir()
            right.mkdir()
            (left / "only_empty").mkdir()
            (right / "shared_empty").mkdir()
            (left / "shared_empty").mkdir()
            (left / "conflict").write_text("file", encoding="utf-8")
            (right / "conflict").mkdir()
            result = compare_folders(left, right)
            entries = {entry.relative_path: entry for entry in result.entries}
            self.assertEqual(entries["only_empty"].status, "only_left")
            self.assertEqual(entries["only_empty"].item_type, "文件夹")
            self.assertEqual(entries["shared_empty"].status, "same")
            self.assertEqual(entries["conflict"].status, "different")
            self.assertEqual(entries["conflict"].item_type, "类型冲突")

    def test_binary_files_are_compared_as_hex_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            left = root / "left.bin"
            right = root / "right.bin"
            left.write_bytes(b"\x00\x01\x02left")
            right.write_bytes(b"\x00\x01\x02right")
            result = compare_files(left, right)
            self.assertFalse(result.text_comparison)
            self.assertTrue(result.hex_comparison)
            self.assertEqual(len(result.rows), 1)
            self.assertEqual(result.rows[0].left_number, 0)
            self.assertTrue(result.rows[0].left_text.startswith("00 01 02 6C 65 66 74"))
            self.assertTrue(result.rows[0].left_text.endswith("|...left|"))
            self.assertTrue(result.rows[0].right_text.startswith("00 01 02 72 69 67 68 74"))
            self.assertTrue(result.rows[0].right_text.endswith("|...right|"))
            self.assertEqual(result.rows[0].status, "different")
            self.assertFalse(result.identical)

    def test_compare_docx_paragraphs_and_tables(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            left = root / "left.docx"
            right = root / "right.docx"
            write_test_docx(left, "第一版说明", "旧值")
            write_test_docx(right, "第二版说明", "新值")
            result = compare_files(left, right, hide_same=False)
            self.assertTrue(result.text_comparison)
            self.assertFalse(result.identical)
            self.assertEqual(len(result.rows), 2)
            self.assertEqual(result.rows[0].left_text.rstrip(), "第一版说明")
            self.assertEqual(result.rows[0].right_text.rstrip(), "第二版说明")
            self.assertEqual(result.rows[1].left_text.rstrip(), "项目\t旧值")
            self.assertEqual(result.rows[1].right_text.rstrip(), "项目\t新值")


if __name__ == "__main__":
    unittest.main()
