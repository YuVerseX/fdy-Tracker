import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from openpyxl import Workbook

from src.services.attachment_service import (
    build_attachment_parse_payload,
    get_attachment_status,
    get_attachment_storage_path,
    parse_attachment_file,
    read_attachment_jobs,
    write_attachment_parse_result,
)


def build_excel_file(file_path: Path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["岗位名称", "招聘人数", "学历要求", "专业要求", "工作地点"])
    sheet.append(["专职辅导员", "2", "硕士", "思想政治教育", "南京"])
    workbook.save(file_path)


class FakePdfPage:
    def __init__(self, text: str):
        self.text = text

    def extract_text(self):
        return self.text


class FakePdfDocument:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class AttachmentServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_attachment_file_should_extract_target_fields_from_xlsx(self):
        file_path = self.temp_path / "jobs.xlsx"
        build_excel_file(file_path)

        fields = parse_attachment_file(str(file_path), "xlsx")
        field_map = {
            field["field_name"]: field["field_value"]
            for field in fields
        }

        self.assertEqual(field_map["岗位名称"], "专职辅导员")
        self.assertEqual(field_map["招聘人数"], "2人")
        self.assertEqual(field_map["学历要求"], "硕士")
        self.assertEqual(field_map["专业要求"], "思想政治教育")
        self.assertEqual(field_map["工作地点"], "南京")

    def test_build_attachment_parse_payload_should_include_job_rows(self):
        file_path = self.temp_path / "jobs.xlsx"
        build_excel_file(file_path)

        payload = build_attachment_parse_payload(str(file_path), "xlsx")

        self.assertEqual(payload["jobs"][0]["job_name"], "专职辅导员")
        self.assertEqual(payload["jobs"][0]["education_requirement"], "硕士")

    def test_parse_attachment_file_should_extract_target_fields_from_pdf(self):
        file_path = self.temp_path / "jobs.pdf"
        file_path.write_bytes(b"%PDF-1.4 fake")
        fake_pdf_module = SimpleNamespace(
            open=lambda _path: FakePdfDocument([
                FakePdfPage("性别要求：男；学历要求：硕士；专业：思想政治教育；工作地点：南京市；招聘人数：2人")
            ])
        )

        with patch("src.services.attachment_service.pdfplumber", fake_pdf_module):
            fields = parse_attachment_file(str(file_path), "pdf")

        field_map = {
            field["field_name"]: field["field_value"]
            for field in fields
        }

        self.assertEqual(field_map["性别要求"], "男")
        self.assertEqual(field_map["学历要求"], "硕士")
        self.assertEqual(field_map["专业要求"], "思想政治教育")
        self.assertEqual(field_map["工作地点"], "南京市")
        self.assertEqual(field_map["招聘人数"], "2人")

    def test_get_attachment_status_should_report_parsed_when_sidecar_exists(self):
        file_path = self.temp_path / "jobs.xlsx"
        build_excel_file(file_path)
        write_attachment_parse_result(
            file_path,
            {
                "filename": "jobs.xlsx",
                "file_type": "xlsx",
                "parser": "table",
                "text_length": 0,
                "fields": [
                    {"field_name": "学历要求", "field_value": "硕士"}
                ],
                "jobs": []
            }
        )

        attachment = SimpleNamespace(
            file_type="xlsx",
            is_downloaded=True,
            local_path=str(file_path)
        )
        status = get_attachment_status(attachment)

        self.assertEqual(status["parse_status"], "已解析")
        self.assertEqual(status["parsed_fields_count"], 1)
        self.assertEqual(status["parser"], "table")
        self.assertEqual(status["text_length"], 0)

    def test_read_attachment_jobs_should_reparse_old_sidecar_without_jobs(self):
        file_path = self.temp_path / "jobs.xlsx"
        build_excel_file(file_path)
        write_attachment_parse_result(
            file_path,
            {
                "filename": "jobs.xlsx",
                "file_type": "xlsx",
                "parser": "table",
                "text_length": 0,
                "fields": [
                    {"field_name": "学历要求", "field_value": "硕士"}
                ]
            }
        )

        jobs = read_attachment_jobs(file_path, "xlsx")

        self.assertEqual(jobs[0]["job_name"], "专职辅导员")

    def test_read_attachment_jobs_should_reparse_old_sidecar_with_empty_jobs(self):
        file_path = self.temp_path / "jobs.xlsx"
        build_excel_file(file_path)
        Path(f"{file_path}.fields.json").write_text(
            """{
  "filename": "jobs.xlsx",
  "file_type": "xlsx",
  "parser": "table",
  "text_length": 0,
  "fields": [],
  "jobs": []
}""",
            encoding="utf-8"
        )

        jobs = read_attachment_jobs(file_path, "xlsx")

        self.assertEqual(jobs[0]["job_name"], "专职辅导员")

    def test_get_attachment_status_should_mark_pdf_as_waiting_parse(self):
        file_path = self.temp_path / "jobs.pdf"
        file_path.write_bytes(b"%PDF-1.4 fake")

        attachment = SimpleNamespace(
            file_type="pdf",
            is_downloaded=True,
            local_path=str(file_path)
        )
        status = get_attachment_status(attachment)

        self.assertTrue(status["is_parseable"])
        self.assertEqual(status["parse_status"], "待解析")

    def test_get_attachment_status_should_mark_old_sidecar_as_waiting_parse(self):
        file_path = self.temp_path / "jobs.xlsx"
        build_excel_file(file_path)
        Path(f"{file_path}.fields.json").write_text(
            """{
  "filename": "jobs.xlsx",
  "file_type": "xlsx",
  "parser": "table",
  "text_length": 0,
  "fields": [
    {"field_name": "学历要求", "field_value": "硕士"}
  ],
  "jobs": []
}""",
            encoding="utf-8"
        )

        attachment = SimpleNamespace(
            file_type="xlsx",
            is_downloaded=True,
            local_path=str(file_path)
        )

        status = get_attachment_status(attachment)

        self.assertEqual(status["parse_status"], "待解析")
        self.assertEqual(status["parsed_fields_count"], 1)

    def test_get_attachment_storage_path_should_prefer_filename_suffix(self):
        with patch(
            "src.services.attachment_service.settings",
            SimpleNamespace(DATA_DIR=self.temp_path)
        ):
            path = get_attachment_storage_path(
                1,
                "岗位表.xlsx",
                "https://example.com/module/download/downfile.jsp?filename=abc123.xlsx"
            )

        self.assertEqual(path.suffix, ".xlsx")


if __name__ == "__main__":
    unittest.main()
