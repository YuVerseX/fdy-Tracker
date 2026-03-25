import unittest

from bs4 import BeautifulSoup

from src.parsers.post_parser import PostParser
from src.scrapers.jiangsu_hrss import (
    JiangsuHRSSScraper,
    build_attachment_filename,
    infer_attachment_type,
    normalize_content_text,
)


class PostParserTestCase(unittest.TestCase):
    def setUp(self):
        self.parser = PostParser()

    def test_extract_gender_should_not_be_misled_by_other_unlimited_fields(self):
        content = """
        性别要求：男
        学历要求：本科及以上
        专业：不限
        """

        self.assertEqual(self.parser.extract_gender(content), "男")

    def test_extract_gender_should_support_job_name_suffix(self):
        content = "岗位名称：专职辅导员（男）"

        self.assertEqual(self.parser.extract_gender(content), "男")

    def test_extract_gender_should_support_explicit_unlimited_keywords(self):
        content = """
        性别不限
        专业：不限
        """

        self.assertEqual(self.parser.extract_gender(content), "不限")

    def test_extract_age_should_support_upper_bound_format(self):
        content = "年龄：35岁以下"

        self.assertEqual(self.parser.extract_age(content), "35岁以下")

    def test_extract_major_should_remove_list_prefix(self):
        content = """
        岗位要求：
        - 思想政治教育专业
        """

        self.assertEqual(self.parser.extract_major(content), "思想政治教育")

    def test_normalize_content_text_should_remove_noise_and_join_broken_lines(self):
        legacy_content = """
        当前位置：
        首页
        >
        资讯中心
        点击查看原文件：
        根据
        202
        5
        年
        11
        月
        24
        日发布公告
        关闭本页
        打印本页
        """

        normalized = normalize_content_text(legacy_content)

        self.assertNotIn("当前位置", normalized)
        self.assertIn("根据2025年11月24日发布公告", normalized)

    def test_normalize_content_text_should_split_attachment_blocks(self):
        content = """
        六、招聘政策咨询江苏护理职业学院人事处负责回答此次招聘政策咨询。咨询电话：0517-80329939
        八、招聘工作举报1.江苏省卫生健康委员会举报电话、传真：025-83620963、832682792.江苏省人力资源和社会保障厅举报信箱：js@example.com
        附件：1.岗位表一2.岗位表二岗位表一.xls岗位表二.xls
        """

        normalized = normalize_content_text(content)

        self.assertIn("六、招聘政策咨询", normalized)
        self.assertIn("\n咨询电话：0517-80329939", normalized)
        self.assertIn("83268279\n2.江苏省人力资源和社会保障厅", normalized)
        self.assertIn("附件：\n1.岗位表一\n2.岗位表二岗位表一.xls\n岗位表二.xls", normalized)

    def test_extract_content_text_should_keep_table_rows_and_split_out_attachments(self):
        scraper = JiangsuHRSSScraper()
        soup = BeautifulSoup(
            """
            <div id="Zoom">
              <p>一、招聘岗位</p>
              <table>
                <tr><th>岗位</th><th>人数</th></tr>
                <tr><td>辅导员</td><td>2</td></tr>
              </table>
              <p>报名时间：2026年3月1日至3月10日</p>
              <p><a href="/files/岗位表.xlsx">附件1：岗位表.xlsx</a></p>
            </div>
            """,
            "html.parser"
        )
        container = soup.select_one("#Zoom")

        attachments = scraper.extract_attachments(container, "https://example.com/detail.html")
        content = scraper.extract_content_text(container, attachments)

        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0]["file_url"], "https://example.com/files/岗位表.xlsx")
        self.assertIn("岗位 | 人数", content)
        self.assertIn("辅导员 | 2", content)
        self.assertIn("报名时间：2026年3月1日至3月10日", content)
        self.assertNotIn("岗位表.xlsx", content)

    def test_build_attachment_filename_should_recover_suffix_from_query_filename(self):
        file_url = "https://example.com/module/download/downfile.jsp?filename=abc123.xlsx"

        filename = build_attachment_filename("岗位表", file_url)
        file_type = infer_attachment_type(filename, file_url)

        self.assertEqual(filename, "岗位表.xlsx")
        self.assertEqual(file_type, "xlsx")

    def test_build_attachment_filename_should_strip_trailing_x_noise(self):
        file_url = "https://example.com/module/download/downfile.jsp?filename=abc123.xls"

        filename = build_attachment_filename("岗位表.xls x", file_url)

        self.assertEqual(filename, "岗位表.xls")

    def test_build_attachment_filename_should_prefer_query_suffix_when_conflict(self):
        file_url = "https://example.com/module/download/downfile.jsp?filename=abc123.xlsx"

        filename = build_attachment_filename("岗位表.xls", file_url)
        file_type = infer_attachment_type(filename, file_url)

        self.assertEqual(filename, "岗位表.xlsx")
        self.assertEqual(file_type, "xlsx")


if __name__ == "__main__":
    unittest.main()
