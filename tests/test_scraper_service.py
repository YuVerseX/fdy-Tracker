import unittest
import inspect
import json
import warnings
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace

from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import sessionmaker

from src.database.models import Attachment, Base, Post, PostAnalysis, PostField, PostInsight, PostJob, Source
from src.scrapers.jiangsu_hrss import JiangsuHRSSScraper
from src.services.ai_analysis_service import ensure_rule_analysis_bundle
from src.services.scraper_service import (
    backfill_existing_attachments,
    create_scraper,
    scrape_and_save,
    should_refresh_post_attachments,
)
from src.services.task_progress import TaskCancellationRequested


def build_excel_bytes(rows):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)

    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content


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


class FakeScraper:
    def __init__(self):
        self.attachment_bytes = build_excel_bytes([
            ["岗位名称", "招聘人数", "学历要求", "工作地点"],
            ["专职辅导员", "2", "硕士", "南京"]
        ])

    async def scrape(self, max_pages=10, progress_callback=None):
        if progress_callback:
            progress_callback({
                "stage": "collecting",
                "stage_key": "collect-pages",
                "stage_label": "正在采集源站页面",
                "progress_mode": "stage_only",
                "metrics": {
                    "pages_fetched": 1,
                    "detail_pages_fetched": 3,
                    "raw_items_collected": 3,
                },
            })
        return [
            {
                "title": "第一条专职辅导员公告",
                "url": "https://example.com/posts/1",
                "publish_date": datetime(2026, 3, 1, tzinfo=timezone.utc),
                "content": "专职辅导员，性别要求：男",
                "attachments": [
                    {
                        "filename": "岗位表.xlsx",
                        "file_url": "https://example.com/files/jobs.xlsx",
                        "file_type": "xlsx"
                    }
                ]
            },
            {
                "title": None,
                "url": "https://example.com/posts/2",
                "publish_date": datetime(2026, 3, 2, tzinfo=timezone.utc),
                "content": "这是一条会失败的数据",
                "attachments": []
            },
            {
                "title": "第三条专职辅导员公告",
                "url": "https://example.com/posts/3",
                "publish_date": datetime(2026, 3, 3, tzinfo=timezone.utc),
                "content": "辅导员，工作地点：南京市",
                "attachments": []
            }
        ]

    async def fetch(self, url: str, method: str = "GET", **kwargs):
        return FakeResponse(self.attachment_bytes)


class ScraperServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test_scraper.db"
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False}
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        Base.metadata.create_all(bind=self.engine)
        self.db = self.SessionLocal()
        self.db.add(Source(
            id=1,
            name="江苏省人力资源和社会保障厅",
            province="江苏",
            source_type="government_website",
            base_url="https://jshrss.jiangsu.gov.cn/col/col80382/index.html",
            scraper_class="JiangsuHRSSScraper",
            is_active=True
        ))
        self.db.commit()

    async def asyncTearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def build_attachment_storage_path(self, post_id: int, filename: str, file_url: str) -> Path:
        safe_name = Path(filename).name or "attachment.bin"
        return Path(self.temp_dir.name) / f"{post_id}_{safe_name}"

    async def test_scrape_and_save_should_require_explicit_source_id(self):
        signature = inspect.signature(scrape_and_save)

        self.assertEqual(signature.parameters["source_id"].default, inspect._empty)

    def test_jiangsu_scraper_default_base_url_should_use_https(self):
        scraper = JiangsuHRSSScraper()

        self.assertEqual(
            scraper.base_url,
            "https://jshrss.jiangsu.gov.cn/col/col80382/index.html",
        )

    def test_create_scraper_should_upgrade_legacy_jiangsu_http_default_to_https(self):
        source = Source(
            id=8,
            name="江苏省人力资源和社会保障厅",
            province="江苏",
            source_type="government_website",
            base_url="http://jshrss.jiangsu.gov.cn/col/col80382/index.html",
            scraper_class="JiangsuHRSSScraper",
            is_active=True,
        )

        scraper = create_scraper(source)

        self.assertEqual(
            scraper.base_url,
            "https://jshrss.jiangsu.gov.cn/col/col80382/index.html",
        )

    def test_create_scraper_should_use_source_base_url_configuration(self):
        source = Source(
            id=9,
            name="示例人社厅",
            province="示例",
            source_type="government_website",
            base_url="https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
            scraper_class="JiangsuHRSSScraper",
            is_active=True,
        )

        scraper = create_scraper(source)

        self.assertIsInstance(scraper, JiangsuHRSSScraper)
        self.assertEqual(
            scraper.base_url,
            "https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
        )
        self.assertEqual(scraper.site_root, "https://jobs.example.gov.cn")
        self.assertEqual(
            scraper.ajax_url,
            "https://jobs.example.gov.cn/module/web/jpage/dataproxy.jsp",
        )
        self.assertEqual(
            scraper.ajax_params,
            {
                "columnid": "90001",
                "unitid": "111",
                "webid": "222",
            },
        )

    def test_create_scraper_should_reject_non_default_source_without_required_ajax_query_params(self):
        source = Source(
            id=10,
            name="缺参数的人社厅",
            province="示例",
            source_type="government_website",
            base_url="https://jobs.example.gov.cn/col/col90001/index.html",
            scraper_class="JiangsuHRSSScraper",
            is_active=True,
        )

        with self.assertRaisesRegex(ValueError, "base_url 缺少必要的 Ajax 参数"):
            create_scraper(source)

    def test_create_scraper_should_reject_blank_source_base_url(self):
        source = Source(
            id=11,
            name="空地址的人社厅",
            province="示例",
            source_type="government_website",
            base_url="   ",
            scraper_class="JiangsuHRSSScraper",
            is_active=True,
        )

        with self.assertRaisesRegex(ValueError, "source base_url 不能为空"):
            create_scraper(source)

    def test_create_scraper_should_reject_none_source_base_url(self):
        source = Source(
            id=12,
            name="空值地址的人社厅",
            province="示例",
            source_type="government_website",
            base_url=None,
            scraper_class="JiangsuHRSSScraper",
            is_active=True,
        )

        with self.assertRaisesRegex(ValueError, "source base_url 不能为空"):
            create_scraper(source)

    async def test_scrape_page_should_build_detail_urls_from_configured_source_origin(self):
        scraper = JiangsuHRSSScraper(
            base_url="https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
        )
        fetch_calls = []
        detail_urls = []

        async def fake_fetch(url: str, method: str = "GET", **kwargs):
            fetch_calls.append((url, method, kwargs.get("params")))
            return SimpleNamespace(
                text="""
<record><![CDATA[
<li>
  <a href="/art/2026/4/3/art_90001_1.html" target="_blank">
    <span class="list_title">示例公告</span>
    <i>2026-04-03</i>
  </a>
</li>
]]></record>
"""
            )

        async def fake_scrape_detail_page(url: str):
            detail_urls.append(url)
            return {"content": "示例正文", "attachments": []}

        async def no_delay():
            return None

        scraper.fetch = fake_fetch
        scraper.scrape_detail_page = fake_scrape_detail_page
        scraper.delay = no_delay

        results = await scraper.scrape_page(2)

        self.assertEqual(
            fetch_calls,
            [
                (
                    "https://jobs.example.gov.cn/module/web/jpage/dataproxy.jsp",
                    "GET",
                    {
                        "columnid": "90001",
                        "unitid": "111",
                        "webid": "222",
                        "page": "2",
                    },
                )
            ],
        )
        self.assertEqual(detail_urls, ["https://jobs.example.gov.cn/art/2026/4/3/art_90001_1.html"])
        self.assertEqual(results[0]["url"], "https://jobs.example.gov.cn/art/2026/4/3/art_90001_1.html")

    async def test_scrape_page_should_resolve_path_relative_detail_urls_against_base_url(self):
        scraper = JiangsuHRSSScraper(
            base_url="https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
        )
        detail_urls = []

        async def fake_fetch(url: str, method: str = "GET", **kwargs):
            return SimpleNamespace(
                text="""
<record><![CDATA[
<li>
  <a href="art/2026/4/3/art_90001_3.html" target="_blank">
    <span class="list_title">相对路径公告</span>
    <i>2026-04-03</i>
  </a>
</li>
]]></record>
"""
            )

        async def fake_scrape_detail_page(url: str):
            detail_urls.append(url)
            return {"content": "相对路径正文", "attachments": []}

        async def no_delay():
            return None

        scraper.fetch = fake_fetch
        scraper.scrape_detail_page = fake_scrape_detail_page
        scraper.delay = no_delay

        results = await scraper.scrape_page(2)

        self.assertEqual(
            detail_urls,
            ["https://jobs.example.gov.cn/col/col90001/art/2026/4/3/art_90001_3.html"],
        )
        self.assertEqual(
            results[0]["url"],
            "https://jobs.example.gov.cn/col/col90001/art/2026/4/3/art_90001_3.html",
        )

    async def test_scrape_first_page_should_build_detail_urls_from_configured_source_origin(self):
        scraper = JiangsuHRSSScraper(
            base_url="https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
        )
        fetch_calls = []
        detail_urls = []

        async def fake_fetch(url: str, method: str = "GET", **kwargs):
            fetch_calls.append((url, method, kwargs.get("params")))
            return SimpleNamespace(
                text="""
<datastore>
  <record><![CDATA[
    <li>
      <a href="/art/2026/4/3/art_90001_2.html" target="_blank">
        <span class="list_title">首页示例公告</span>
        <i>2026-04-03</i>
      </a>
    </li>
  ]]></record>
</datastore>
"""
            )

        async def fake_scrape_detail_page(url: str):
            detail_urls.append(url)
            return {"content": "首页示例正文", "attachments": []}

        async def no_delay():
            return None

        scraper.fetch = fake_fetch
        scraper.scrape_detail_page = fake_scrape_detail_page
        scraper.delay = no_delay

        results = await scraper.scrape_first_page()

        self.assertEqual(
            fetch_calls,
            [
                (
                    "https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
                    "GET",
                    None,
                )
            ],
        )
        self.assertEqual(detail_urls, ["https://jobs.example.gov.cn/art/2026/4/3/art_90001_2.html"])
        self.assertEqual(results[0]["url"], "https://jobs.example.gov.cn/art/2026/4/3/art_90001_2.html")

    async def test_scrape_should_emit_detail_failure_and_skipped_metrics(self):
        scraper = JiangsuHRSSScraper(
            base_url="https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
        )
        updates = []

        async def fake_fetch(url: str, method: str = "GET", **kwargs):
            return SimpleNamespace(
                text="""
<datastore>
  <record><![CDATA[
    <li>
      <a href="/art/2026/4/3/art_90001_1.html" target="_blank">
        <span class="list_title">详情失败公告</span>
        <i>2026-04-03</i>
      </a>
    </li>
  ]]></record>
  <record><![CDATA[
    <li>
      <a href="/art/2026/4/3/art_90001_2.html" target="_blank">
        <i>2026-04-03</i>
      </a>
    </li>
  ]]></record>
</datastore>
"""
            )

        async def fake_scrape_detail_page(url: str):
            return {"content": "", "attachments": [], "detail_failed": True}

        async def no_delay():
            return None

        scraper.fetch = fake_fetch
        scraper.scrape_detail_page = fake_scrape_detail_page
        scraper.delay = no_delay

        results = await scraper.scrape(max_pages=1, progress_callback=updates.append)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "详情失败公告")
        self.assertEqual(results[0]["content"], "")
        self.assertEqual(updates[0]["metrics"]["detail_failures"], 1)
        self.assertEqual(updates[0]["metrics"]["skipped_items"], 1)
        self.assertEqual(updates[0]["metrics"]["raw_items_collected"], 1)

    async def test_scrape_should_emit_page_failure_metrics_when_following_page_fails(self):
        scraper = JiangsuHRSSScraper(
            base_url="https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
        )
        updates = []

        async def fake_scrape_first_page():
            return [
                {
                    "title": "首页公告",
                    "url": "https://jobs.example.gov.cn/art/2026/4/3/art_90001_1.html",
                    "publish_date": datetime(2026, 4, 3, tzinfo=timezone.utc),
                    "content": "首页正文",
                    "attachments": [],
                }
            ]

        async def fake_scrape_page(page_num: int):
            raise RuntimeError(f"ajax unavailable: {page_num}")

        async def no_delay():
            return None

        scraper.scrape_first_page = fake_scrape_first_page
        scraper.scrape_page = fake_scrape_page
        scraper.delay = no_delay

        results = await scraper.scrape(max_pages=3, progress_callback=updates.append)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(updates), 2)
        self.assertEqual(updates[-1]["metrics"]["page_failures"], 1)
        self.assertEqual(updates[-1]["metrics"]["pages_fetched"], 1)
        self.assertEqual(updates[-1]["metrics"]["raw_items_collected"], 1)

    async def test_scrape_should_skip_record_without_href_instead_of_reusing_base_url(self):
        scraper = JiangsuHRSSScraper(
            base_url="https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
        )
        updates = []
        detail_urls = []

        async def fake_fetch(url: str, method: str = "GET", **kwargs):
            return SimpleNamespace(
                text="""
<datastore>
  <record><![CDATA[
    <li>
      <a target="_blank">
        <span class="list_title">缺链接公告</span>
        <i>2026-04-03</i>
      </a>
    </li>
  ]]></record>
  <record><![CDATA[
    <li>
      <a href="/art/2026/4/3/art_90001_1.html" target="_blank">
        <span class="list_title">有效公告</span>
        <i>2026-04-03</i>
      </a>
    </li>
  ]]></record>
</datastore>
"""
            )

        async def fake_scrape_detail_page(url: str):
            detail_urls.append(url)
            return {"content": "有效正文", "attachments": [], "detail_failed": False}

        async def no_delay():
            return None

        scraper.fetch = fake_fetch
        scraper.scrape_detail_page = fake_scrape_detail_page
        scraper.delay = no_delay

        results = await scraper.scrape(max_pages=1, progress_callback=updates.append)

        self.assertEqual(len(results), 1)
        self.assertEqual(detail_urls, ["https://jobs.example.gov.cn/art/2026/4/3/art_90001_1.html"])
        self.assertEqual(updates[0]["metrics"]["skipped_items"], 1)

    async def test_scrape_should_emit_empty_following_page_as_fetched_page(self):
        scraper = JiangsuHRSSScraper(
            base_url="https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
        )
        updates = []

        async def fake_scrape_first_page():
            return [
                {
                    "title": "首页公告",
                    "url": "https://jobs.example.gov.cn/art/2026/4/3/art_90001_1.html",
                    "publish_date": datetime(2026, 4, 3, tzinfo=timezone.utc),
                    "content": "首页正文",
                    "attachments": [],
                }
            ]

        async def fake_scrape_page(page_num: int):
            return []

        async def no_delay():
            return None

        scraper.scrape_first_page = fake_scrape_first_page
        scraper.scrape_page = fake_scrape_page
        scraper.delay = no_delay

        results = await scraper.scrape(max_pages=3, progress_callback=updates.append)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(updates), 2)
        self.assertEqual(updates[-1]["metrics"]["pages_fetched"], 2)
        self.assertEqual(updates[-1]["metrics"]["page_failures"], 0)

    async def test_scrape_should_emit_first_page_failure_metrics_before_raising(self):
        scraper = JiangsuHRSSScraper(
            base_url="https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
        )
        updates = []

        async def fake_scrape_first_page():
            raise RuntimeError("homepage unavailable")

        scraper.scrape_first_page = fake_scrape_first_page

        with self.assertRaisesRegex(RuntimeError, "homepage unavailable"):
            await scraper.scrape(max_pages=3, progress_callback=updates.append)

        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["metrics"]["page_failures"], 1)
        self.assertEqual(updates[0]["metrics"]["pages_fetched"], 0)

    async def test_scrape_should_treat_missing_datastore_as_first_page_failure(self):
        scraper = JiangsuHRSSScraper(
            base_url="https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
        )
        updates = []

        async def fake_fetch(url: str, method: str = "GET", **kwargs):
            return SimpleNamespace(text="<html><body>nginx 404 page</body></html>")

        async def no_delay():
            return None

        scraper.fetch = fake_fetch
        scraper.delay = no_delay

        with self.assertRaisesRegex(RuntimeError, "首页响应结构不符合预期"):
            await scraper.scrape(max_pages=3, progress_callback=updates.append)

        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["metrics"]["page_failures"], 1)
        self.assertEqual(updates[0]["metrics"]["pages_fetched"], 0)

    async def test_scrape_should_treat_malformed_datastore_as_first_page_failure(self):
        scraper = JiangsuHRSSScraper(
            base_url="https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
        )
        updates = []

        async def fake_fetch(url: str, method: str = "GET", **kwargs):
            return SimpleNamespace(text="<datastore><div>oops</div></datastore>")

        async def no_delay():
            return None

        scraper.fetch = fake_fetch
        scraper.delay = no_delay

        with self.assertRaisesRegex(RuntimeError, "首页响应结构不符合预期"):
            await scraper.scrape(max_pages=3, progress_callback=updates.append)

        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["metrics"]["page_failures"], 1)
        self.assertEqual(updates[0]["metrics"]["pages_fetched"], 0)

    async def test_scrape_should_count_invalid_ajax_payload_as_page_failure(self):
        scraper = JiangsuHRSSScraper(
            base_url="https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
        )
        updates = []

        async def fake_scrape_first_page():
            return [
                {
                    "title": "首页公告",
                    "url": "https://jobs.example.gov.cn/art/2026/4/3/art_90001_1.html",
                    "publish_date": datetime(2026, 4, 3, tzinfo=timezone.utc),
                    "content": "首页正文",
                    "attachments": [],
                }
            ]

        async def fake_fetch(url: str, method: str = "GET", **kwargs):
            return SimpleNamespace(text="<html><body>ajax error page</body></html>")

        async def no_delay():
            return None

        scraper.scrape_first_page = fake_scrape_first_page
        scraper.fetch = fake_fetch
        scraper.delay = no_delay

        results = await scraper.scrape(max_pages=3, progress_callback=updates.append)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(updates), 2)
        self.assertEqual(updates[-1]["metrics"]["page_failures"], 1)
        self.assertEqual(updates[-1]["metrics"]["pages_fetched"], 1)

    async def test_scrape_detail_page_should_mark_error_html_as_failed(self):
        scraper = JiangsuHRSSScraper(
            base_url="https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
        )

        async def fake_fetch(url: str, method: str = "GET", **kwargs):
            return SimpleNamespace(
                text="<html><head><title>404 Not Found</title></head><body>nginx 404 Not Found</body></html>"
            )

        scraper.fetch = fake_fetch

        payload = await scraper.scrape_detail_page("https://jobs.example.gov.cn/art/2026/4/3/art_90001_404.html")

        self.assertTrue(payload["detail_failed"])
        self.assertEqual(payload["content"], "")
        self.assertEqual(payload["attachments"], [])

    async def test_scrape_detail_page_should_mark_error_html_inside_content_container_as_failed(self):
        scraper = JiangsuHRSSScraper(
            base_url="https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
        )

        async def fake_fetch(url: str, method: str = "GET", **kwargs):
            return SimpleNamespace(
                text="""
<html>
  <head><title>404 Not Found</title></head>
  <body>
    <div class="content">404 Not Found</div>
  </body>
</html>
"""
            )

        scraper.fetch = fake_fetch

        payload = await scraper.scrape_detail_page("https://jobs.example.gov.cn/art/2026/4/3/art_90001_404_container.html")

        self.assertTrue(payload["detail_failed"])
        self.assertEqual(payload["content"], "")
        self.assertEqual(payload["attachments"], [])

    async def test_scrape_detail_page_should_extract_attachment_from_query_param_url_with_tail_params(self):
        scraper = JiangsuHRSSScraper(
            base_url="https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
        )

        async def fake_fetch(url: str, method: str = "GET", **kwargs):
            return SimpleNamespace(
                text="""
<html>
  <body>
    <div class="content">
      <p>详见附件岗位表。</p>
      <a href="/module/download/downfile.jsp?filename=jobs.xlsx&wbfileid=123">点击下载</a>
    </div>
  </body>
</html>
"""
            )

        scraper.fetch = fake_fetch

        payload = await scraper.scrape_detail_page("https://jobs.example.gov.cn/art/2026/4/3/art_90001_attachment.html")

        self.assertFalse(payload["detail_failed"])
        self.assertEqual(len(payload["attachments"]), 1)
        self.assertEqual(payload["attachments"][0]["filename"], "jobs.xlsx")
        self.assertEqual(payload["attachments"][0]["file_type"], "xlsx")

    async def test_scrape_and_save_should_keep_other_records_when_one_record_fails(self):
        with patch("src.services.scraper_service.create_scraper", return_value=FakeScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ):
            result = await scrape_and_save(self.db, source_id=1, max_pages=3)

        saved_posts = self.db.query(Post).order_by(Post.id).all()

        self.assertIsInstance(result, dict)
        self.assertEqual(result["processed_records"], 2)
        self.assertEqual(result["posts_created"], 2)
        self.assertEqual(result["posts_updated"], 0)
        self.assertEqual(result["failures"], 1)
        self.assertEqual(len(saved_posts), 2)
        self.assertEqual(saved_posts[0].title, "第一条专职辅导员公告")
        self.assertEqual(saved_posts[1].title, "第三条专职辅导员公告")
        self.assertEqual(self.db.query(Attachment).count(), 1)
        self.assertEqual(self.db.query(PostAnalysis).count(), 2)
        self.assertEqual(self.db.query(PostInsight).count(), 2)
        self.assertEqual(self.db.query(PostJob).count(), 2)
        saved_attachment = self.db.query(Attachment).first()
        self.assertTrue(saved_attachment.is_downloaded)
        self.assertTrue(Path(saved_attachment.local_path).exists())
        field_names = {
            field.field_name
            for field in self.db.query(PostField).filter(PostField.post_id == saved_posts[0].id).all()
        }
        self.assertIn("学历要求", field_names)
        self.assertIn("工作地点", field_names)
        first_analysis = self.db.query(PostAnalysis).filter(PostAnalysis.post_id == saved_posts[0].id).first()
        first_insight = self.db.query(PostInsight).filter(PostInsight.post_id == saved_posts[0].id).first()
        self.assertIsNotNone(first_analysis)
        self.assertIsNotNone(first_insight)
        self.assertEqual(first_analysis.event_type, "招聘公告")
        self.assertEqual(first_insight.insight_provider, "rule")
        first_post_jobs = self.db.query(PostJob).filter(PostJob.post_id == saved_posts[0].id).all()
        self.assertEqual(first_post_jobs[0].job_name, "专职辅导员")
        self.assertEqual(saved_posts[0].counselor_scope, "dedicated")

    async def test_scrape_and_save_should_skip_detail_failed_record_from_scrape_results(self):
        class DetailFailedScraper:
            async def scrape(self, max_pages=10, progress_callback=None):
                return [
                    {
                        "title": "详情失败公告",
                        "url": "https://example.com/detail-failed",
                        "publish_date": datetime(2026, 3, 4, tzinfo=timezone.utc),
                        "content": "",
                        "attachments": [],
                        "detail_failed": True,
                    }
                ]

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(b"")

        with patch("src.services.scraper_service.create_scraper", return_value=DetailFailedScraper()):
            result = await scrape_and_save(self.db, source_id=1, max_pages=1)

        self.assertEqual(result["processed_records"], 0)
        self.assertEqual(result["posts_created"], 0)
        self.assertEqual(result["posts_updated"], 0)
        self.assertEqual(result["failures"], 1)
        self.assertEqual(self.db.query(Post).count(), 0)

    async def test_scrape_and_save_should_remove_stale_attachments_fields_and_jobs_when_attachment_list_becomes_empty(self):
        existing_post = Post(
            source_id=1,
            title="某高校工作人员公告",
            content="详见附件岗位表。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/attachment-empty-refresh",
            original_url="https://example.com/attachment-empty-refresh",
            is_counselor=True,
            confidence_score=0.7,
        )
        self.db.add(existing_post)
        self.db.flush()
        attachment_path = self.build_attachment_storage_path(
            existing_post.id,
            "岗位表.xlsx",
            "https://example.com/files/attachment-empty-refresh.xlsx",
        )
        attachment_path.write_bytes(build_excel_bytes([
            ["岗位", "人数", "学历", "地点"],
            ["辅导员", "2", "硕士", "南京"],
        ]))
        self.db.add(Attachment(
            post_id=existing_post.id,
            filename="岗位表.xlsx",
            file_url="https://example.com/files/attachment-empty-refresh.xlsx",
            file_type="xlsx",
            is_downloaded=True,
            local_path=str(attachment_path),
            file_size=attachment_path.stat().st_size,
        ))
        self.db.add(PostField(post_id=existing_post.id, field_name="学历要求", field_value="硕士"))
        self.db.add(PostJob(
            post_id=existing_post.id,
            job_name="辅导员",
            recruitment_count="2人",
            source_type="attachment",
            is_counselor=True,
            confidence_score=0.8,
            raw_payload_json=json.dumps({"岗位名称": "辅导员"}, ensure_ascii=False),
            sort_order=0,
        ))
        self.db.commit()

        class AttachmentRemovedScraper:
            async def scrape(self, max_pages=10, progress_callback=None):
                return [
                    {
                        "title": "某高校工作人员公告",
                        "url": "https://example.com/attachment-empty-refresh",
                        "publish_date": datetime(2026, 3, 1, tzinfo=timezone.utc),
                        "content": "详见附件岗位表。",
                        "attachments": [],
                    }
                ]

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(b"")

        with patch("src.services.scraper_service.create_scraper", return_value=AttachmentRemovedScraper()):
            result = await scrape_and_save(self.db, source_id=1, max_pages=1)

        self.assertEqual(result["processed_records"], 1)
        self.assertEqual(result["posts_updated"], 1)
        self.assertEqual(self.db.query(Attachment).filter(Attachment.post_id == existing_post.id).count(), 0)
        self.assertEqual(self.db.query(PostField).filter(PostField.post_id == existing_post.id).count(), 0)
        self.assertEqual(self.db.query(PostJob).filter(PostJob.post_id == existing_post.id).count(), 0)

    async def test_scrape_and_save_should_report_record_level_failures(self):
        with patch("src.services.scraper_service.create_scraper", return_value=FakeScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ):
            result = await scrape_and_save(self.db, source_id=1, max_pages=3)

        self.assertEqual(result["processed_records"], 2)
        self.assertEqual(result["posts_created"], 2)
        self.assertEqual(result["posts_updated"], 0)
        self.assertEqual(result["failures"], 1)

    async def test_scrape_and_save_should_trigger_analysis_bundle_for_new_posts(self):
        with patch("src.services.scraper_service.create_scraper", return_value=FakeScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ), patch(
            "src.services.scraper_service.ensure_rule_analysis_bundle",
        ) as mocked_bundle:
            result = await scrape_and_save(self.db, source_id=1, max_pages=3)

        called_post_ids = [call.args[1].id for call in mocked_bundle.call_args_list]

        self.assertEqual(result["processed_records"], 2)
        self.assertEqual(mocked_bundle.call_count, 2)
        self.assertCountEqual(called_post_ids, [1, 2])

    async def test_scrape_and_save_should_mark_duplicate_posts_after_save(self):
        with patch("src.services.scraper_service.create_scraper", return_value=FakeScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ), patch(
            "src.services.scraper_service.refresh_duplicate_posts",
            return_value={"scanned": 2, "groups": 1, "duplicates": 1},
        ) as mocked_refresh:
            result = await scrape_and_save(self.db, source_id=1, max_pages=3)

        self.assertGreaterEqual(result["processed_records"], 1)
        mocked_refresh.assert_called_once()
        called_post_ids = mocked_refresh.call_args.args[1]
        self.assertIsInstance(called_post_ids, list)
        self.assertGreaterEqual(len(called_post_ids), 1)

    async def test_scrape_and_save_should_emit_progress_metrics(self):
        updates = []

        with patch("src.services.scraper_service.create_scraper", return_value=FakeScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ):
            result = await scrape_and_save(
                self.db,
                source_id=1,
                max_pages=1,
                progress_callback=updates.append,
            )

        persisting_updates = [update for update in updates if update["stage"] == "persisting"]

        self.assertEqual(len(persisting_updates), 3)
        self.assertEqual([update["stage_key"] for update in persisting_updates], ["persist-posts"] * 3)
        self.assertEqual(
            [update["metrics"]["posts_seen"] for update in persisting_updates],
            [1, 2, 3],
        )
        self.assertEqual(
            [update["metrics"]["posts_created"] for update in persisting_updates],
            [1, 1, 2],
        )
        self.assertEqual(persisting_updates[-1]["metrics"]["posts_total"], 3)
        self.assertEqual(persisting_updates[-1]["metrics"]["posts_created"], result["posts_created"])
        self.assertEqual(persisting_updates[-1]["metrics"]["posts_updated"], 0)
        self.assertEqual(persisting_updates[-1]["metrics"]["failures"], 1)

    async def test_scrape_and_save_should_emit_collecting_then_persisting_progress(self):
        updates = []

        with patch("src.services.scraper_service.create_scraper", return_value=FakeScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ):
            result = await scrape_and_save(
                self.db,
                source_id=1,
                max_pages=1,
                progress_callback=updates.append,
            )

        self.assertEqual(updates[0]["stage"], "collecting")
        self.assertEqual(updates[0]["metrics"]["pages_fetched"], 1)
        self.assertEqual(updates[0]["metrics"]["raw_items_collected"], 3)
        self.assertTrue(all(update["stage"] == "persisting" for update in updates[1:]))
        self.assertEqual(updates[-1]["metrics"]["posts_total"], 3)
        self.assertEqual(result["posts_created"], 2)

    async def test_scrape_and_save_should_raise_when_scraper_creation_fails(self):
        with patch(
            "src.services.scraper_service.create_scraper",
            side_effect=ValueError("未注册的爬虫类: MissingScraper"),
        ):
            with self.assertRaisesRegex(RuntimeError, "未注册的爬虫类"):
                await scrape_and_save(self.db, source_id=1, max_pages=1)

    async def test_scrape_and_save_should_raise_when_scrape_request_fails(self):
        class BrokenScraper:
            async def scrape(self, max_pages=10, progress_callback=None):
                raise RuntimeError("源站超时")

        with patch(
            "src.services.scraper_service.create_scraper",
            return_value=BrokenScraper(),
        ):
            with self.assertRaisesRegex(RuntimeError, "源站超时"):
                await scrape_and_save(self.db, source_id=1, max_pages=1)

    async def test_scrape_and_save_should_raise_when_commit_fails(self):
        with patch("src.services.scraper_service.create_scraper", return_value=FakeScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ), patch.object(
            self.db,
            "commit",
            side_effect=RuntimeError("提交失败"),
        ):
            with self.assertRaisesRegex(RuntimeError, "提交失败"):
                await scrape_and_save(self.db, source_id=1, max_pages=1)

    async def test_scrape_and_save_should_raise_for_inactive_source(self):
        source = self.db.query(Source).filter(Source.id == 1).first()
        source.is_active = False
        self.db.commit()

        with self.assertRaisesRegex(RuntimeError, "数据源已停用"):
            await scrape_and_save(self.db, source_id=1, max_pages=1)

    async def test_scrape_and_save_should_sync_attachments_for_existing_post(self):
        existing_post = Post(
            source_id=1,
            title="已有公告",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/existing",
            original_url="https://example.com/existing",
            is_counselor=True,
            confidence_score=0.9
        )
        self.db.add(existing_post)
        self.db.commit()

        attachment_bytes = build_excel_bytes([
            ["岗位", "人数", "学历", "地点"],
            ["辅导员", "3", "本科", "苏州"]
        ])

        class ExistingPostScraper:
            async def scrape(self, max_pages=10, progress_callback=None):
                return [
                    {
                        "title": "已有公告",
                        "url": "https://example.com/existing",
                        "publish_date": datetime(2026, 3, 1, tzinfo=timezone.utc),
                        "content": "已有正文",
                        "attachments": [
                            {
                                "filename": "附件一.xlsx",
                                "file_url": "https://example.com/files/attachment-1.xlsx",
                                "file_type": "xlsx"
                            }
                        ]
                    }
                ]

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(attachment_bytes)

        with patch("src.services.scraper_service.create_scraper", return_value=ExistingPostScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ):
            result = await scrape_and_save(self.db, source_id=1, max_pages=1)

        attachments = self.db.query(Attachment).filter(Attachment.post_id == existing_post.id).all()
        fields = {
            field.field_name: field.field_value
            for field in self.db.query(PostField).filter(PostField.post_id == existing_post.id).all()
        }

        self.assertEqual(result["processed_records"], 1)
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].filename, "附件一.xlsx")
        self.assertTrue(attachments[0].is_downloaded)
        self.assertEqual(fields["学历要求"], "本科")
        self.assertEqual(fields["工作地点"], "苏州")
        analysis = self.db.query(PostAnalysis).filter(PostAnalysis.post_id == existing_post.id).first()
        jobs = self.db.query(PostJob).filter(PostJob.post_id == existing_post.id).all()
        self.assertIsNotNone(analysis)
        self.assertEqual(analysis.analysis_provider, "rule")
        self.assertEqual(jobs[0].job_name, "辅导员")
        self.assertEqual(existing_post.counselor_scope, "contains")

    async def test_scrape_and_save_should_trigger_bundle_for_existing_posts_without_overwriting_openai_insight(self):
        existing_post = Post(
            source_id=1,
            title="已有 OpenAI 洞察公告",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/existing-openai-insight",
            original_url="https://example.com/existing-openai-insight",
            is_counselor=True,
            confidence_score=0.9,
        )
        self.db.add(existing_post)
        self.db.flush()
        self.db.add(PostInsight(
            post_id=existing_post.id,
            insight_status="success",
            insight_provider="openai",
            model_name="gpt-5.4",
            prompt_version="v1",
            recruitment_count_total=2,
            counselor_recruitment_count=2,
            degree_floor="硕士",
            city_list_json=json.dumps(["南京"], ensure_ascii=False),
            gender_restriction="不限",
            political_status_required="中共党员",
            deadline_text="2026年4月1日",
            deadline_date="2026-04-01",
            deadline_status="报名中",
            has_written_exam=True,
            has_interview=True,
            has_attachment_job_table=True,
            evidence_summary="已有 OpenAI insight",
            raw_result_json="{}",
            analyzed_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        ))
        self.db.commit()

        attachment_bytes = build_excel_bytes([
            ["岗位", "人数", "学历", "地点"],
            ["辅导员", "3", "本科", "苏州"]
        ])

        class ExistingPostScraper:
            async def scrape(self, max_pages=10, progress_callback=None):
                return [
                    {
                        "title": "已有 OpenAI 洞察公告",
                        "url": "https://example.com/existing-openai-insight",
                        "publish_date": datetime(2026, 3, 1, tzinfo=timezone.utc),
                        "content": "已有正文",
                        "attachments": [
                            {
                                "filename": "附件一.xlsx",
                                "file_url": "https://example.com/files/attachment-openai.xlsx",
                                "file_type": "xlsx"
                            }
                        ]
                    }
                ]

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(attachment_bytes)

        with patch("src.services.scraper_service.create_scraper", return_value=ExistingPostScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ), patch(
            "src.services.scraper_service.ensure_rule_analysis_bundle",
            wraps=ensure_rule_analysis_bundle,
        ) as mocked_bundle:
            result = await scrape_and_save(self.db, source_id=1, max_pages=1)

        saved_insight = self.db.query(PostInsight).filter(PostInsight.post_id == existing_post.id).first()

        self.assertEqual(result["processed_records"], 1)
        self.assertEqual(mocked_bundle.call_count, 1)
        self.assertEqual(mocked_bundle.call_args.args[1].id, existing_post.id)
        self.assertEqual(saved_insight.insight_provider, "openai")
        self.assertEqual(saved_insight.evidence_summary, "已有 OpenAI insight")

    async def test_scrape_and_save_should_refresh_attachment_metadata_when_url_same(self):
        existing_post = Post(
            source_id=1,
            title="已有公告",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/metadata-fix",
            original_url="https://example.com/metadata-fix",
            is_counselor=True,
            confidence_score=0.9
        )
        self.db.add(existing_post)
        self.db.flush()
        self.db.add(Attachment(
            post_id=existing_post.id,
            filename="downfile.jsp",
            file_url="https://example.com/module/download/downfile.jsp?filename=attachment-1.xlsx",
            file_type="",
            is_downloaded=False,
            local_path=None
        ))
        self.db.commit()

        attachment_bytes = build_excel_bytes([
            ["岗位", "人数", "学历", "地点"],
            ["辅导员", "3", "本科", "苏州"]
        ])

        class MetadataRefreshScraper:
            async def scrape(self, max_pages=10, progress_callback=None):
                return [
                    {
                        "title": "已有公告",
                        "url": "https://example.com/metadata-fix",
                        "publish_date": datetime(2026, 3, 1, tzinfo=timezone.utc),
                        "content": "已有正文",
                        "attachments": [
                            {
                                "filename": "岗位表.xlsx",
                                "file_url": "https://example.com/module/download/downfile.jsp?filename=attachment-1.xlsx",
                                "file_type": "xlsx"
                            }
                        ]
                    }
                ]

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(attachment_bytes)

        with patch("src.services.scraper_service.create_scraper", return_value=MetadataRefreshScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ):
            result = await scrape_and_save(self.db, source_id=1, max_pages=1)

        attachment = self.db.query(Attachment).filter(Attachment.post_id == existing_post.id).first()

        self.assertEqual(result["processed_records"], 1)
        self.assertEqual(attachment.filename, "岗位表.xlsx")
        self.assertEqual(attachment.file_type, "xlsx")
        self.assertTrue(attachment.is_downloaded)

    async def test_scrape_and_save_should_refresh_existing_post_content_fields_and_publish_date(self):
        existing_post = Post(
            source_id=1,
            title="旧公告标题",
            content="学历要求：本科；工作地点：南京。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/post-refresh",
            original_url="https://example.com/post-refresh",
            is_counselor=True,
            confidence_score=0.7,
        )
        self.db.add(existing_post)
        self.db.flush()
        self.db.add_all([
            PostField(post_id=existing_post.id, field_name="学历要求", field_value="本科"),
            PostField(post_id=existing_post.id, field_name="工作地点", field_value="南京"),
        ])
        self.db.commit()

        class RefreshingScraper:
            async def scrape(self, max_pages=10, progress_callback=None):
                return [
                    {
                        "title": "新公告标题",
                        "url": "https://example.com/post-refresh",
                        "publish_date": datetime(2026, 3, 8, tzinfo=timezone.utc),
                        "content": "学历要求：博士；工作地点：苏州。",
                        "attachments": [],
                    }
                ]

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(b"")

        with patch("src.services.scraper_service.create_scraper", return_value=RefreshingScraper()):
            result = await scrape_and_save(self.db, source_id=1, max_pages=1)

        saved_post = self.db.query(Post).filter(Post.id == existing_post.id).first()
        field_map = {
            field.field_name: field.field_value
            for field in self.db.query(PostField).filter(PostField.post_id == existing_post.id).all()
        }

        self.assertEqual(result["processed_records"], 1)
        self.assertEqual(result["posts_updated"], 1)
        self.assertEqual(saved_post.title, "新公告标题")
        self.assertEqual(saved_post.content, "学历要求：博士；工作地点：苏州。")
        self.assertEqual(saved_post.publish_date.date().isoformat(), "2026-03-08")
        self.assertEqual(field_map["学历要求"], "博士")
        self.assertEqual(field_map["工作地点"], "苏州")

    async def test_scrape_and_save_should_refresh_attachment_fields_without_sawarning(self):
        existing_post = Post(
            source_id=1,
            title="已有公告",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/attachment-refresh",
            original_url="https://example.com/attachment-refresh",
            is_counselor=True,
            confidence_score=0.9,
        )
        self.db.add(existing_post)
        self.db.flush()
        self.db.add(PostField(post_id=existing_post.id, field_name="学历要求", field_value="本科"))
        self.db.add(Attachment(
            post_id=existing_post.id,
            filename="downfile.jsp",
            file_url="https://example.com/module/download/downfile.jsp?filename=attachment-1.xlsx",
            file_type="",
            is_downloaded=False,
            local_path=None,
        ))
        self.db.commit()

        attachment_bytes = build_excel_bytes([
            ["岗位", "人数", "学历", "地点"],
            ["辅导员", "5", "博士", "苏州"],
        ])

        class AttachmentRefreshingScraper:
            async def scrape(self, max_pages=10, progress_callback=None):
                return [
                    {
                        "title": "已有公告",
                        "url": "https://example.com/attachment-refresh",
                        "publish_date": datetime(2026, 3, 1, tzinfo=timezone.utc),
                        "content": "已有正文",
                        "attachments": [
                            {
                                "filename": "岗位表.xlsx",
                                "file_url": "https://example.com/module/download/downfile.jsp?filename=attachment-1.xlsx",
                                "file_type": "xlsx",
                            }
                        ],
                    }
                ]

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(attachment_bytes)

        with patch("src.services.scraper_service.create_scraper", return_value=AttachmentRefreshingScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path,
        ), warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            result = await scrape_and_save(self.db, source_id=1, max_pages=1)

        attachment = self.db.query(Attachment).filter(Attachment.post_id == existing_post.id).first()
        field_map = {
            field.field_name: field.field_value
            for field in self.db.query(PostField).filter(PostField.post_id == existing_post.id).all()
        }

        self.assertEqual(result["processed_records"], 1)
        self.assertEqual(result["posts_updated"], 1)
        self.assertEqual(attachment.filename, "岗位表.xlsx")
        self.assertEqual(attachment.file_type, "xlsx")
        self.assertEqual(field_map["学历要求"], "博士")
        self.assertFalse(any(item.category is SAWarning for item in caught_warnings))

    async def test_scrape_and_save_should_redownload_same_attachment_url_when_attachment_content_changes(self):
        existing_post = Post(
            source_id=1,
            title="已有公告",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/attachment-binary-refresh",
            original_url="https://example.com/attachment-binary-refresh",
            is_counselor=True,
            confidence_score=0.9,
        )
        self.db.add(existing_post)
        self.db.flush()

        attachment_path = self.build_attachment_storage_path(
            existing_post.id,
            "岗位表.xlsx",
            "https://example.com/files/jobs.xlsx",
        )
        attachment_path.write_bytes(build_excel_bytes([
            ["岗位", "人数", "学历", "地点"],
            ["辅导员", "2", "本科", "南京"],
        ]))
        self.db.add(PostField(post_id=existing_post.id, field_name="学历要求", field_value="本科"))
        self.db.add(Attachment(
            post_id=existing_post.id,
            filename="岗位表.xlsx",
            file_url="https://example.com/files/jobs.xlsx",
            file_type="xlsx",
            is_downloaded=True,
            local_path=str(attachment_path),
            file_size=attachment_path.stat().st_size,
        ))
        self.db.commit()

        refreshed_attachment_bytes = build_excel_bytes([
            ["岗位", "人数", "学历", "地点"],
            ["辅导员", "4", "博士", "苏州"],
        ])

        class AttachmentBinaryRefreshingScraper:
            async def scrape(self, max_pages=10, progress_callback=None):
                return [
                    {
                        "title": "已有公告",
                        "url": "https://example.com/attachment-binary-refresh",
                        "publish_date": datetime(2026, 3, 1, tzinfo=timezone.utc),
                        "content": "已有正文",
                        "attachments": [
                            {
                                "filename": "岗位表.xlsx",
                                "file_url": "https://example.com/files/jobs.xlsx",
                                "file_type": "xlsx",
                            }
                        ],
                    }
                ]

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(refreshed_attachment_bytes)

        with patch("src.services.scraper_service.create_scraper", return_value=AttachmentBinaryRefreshingScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path,
        ):
            result = await scrape_and_save(self.db, source_id=1, max_pages=1)

        field_map = {
            field.field_name: field.field_value
            for field in self.db.query(PostField).filter(PostField.post_id == existing_post.id).all()
        }
        saved_jobs = self.db.query(PostJob).filter(PostJob.post_id == existing_post.id).all()

        self.assertEqual(result["processed_records"], 1)
        self.assertEqual(result["posts_updated"], 1)
        self.assertEqual(field_map["学历要求"], "博士")
        self.assertEqual(saved_jobs[0].recruitment_count, "4人")

    async def test_backfill_existing_attachments_should_discover_and_parse_history_attachments(self):
        existing_post = Post(
            source_id=1,
            title="历史辅导员公告",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/history",
            original_url="https://example.com/history",
            is_counselor=True,
            confidence_score=0.95
        )
        self.db.add(existing_post)
        self.db.commit()

        attachment_bytes = build_excel_bytes([
            ["岗位名称", "招聘人数", "学历要求", "工作地点"],
            ["专职辅导员", "4", "博士", "无锡"]
        ])

        class HistoryBackfillScraper:
            async def scrape_detail_page(self, url: str):
                return {
                    "content": "已有正文",
                    "attachments": [
                        {
                            "filename": "历史岗位表.xlsx",
                            "file_url": "https://example.com/files/history.xlsx",
                            "file_type": "xlsx"
                        }
                    ]
                }

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(attachment_bytes)

        with patch("src.services.scraper_service.create_scraper", return_value=HistoryBackfillScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ):
            result = await backfill_existing_attachments(self.db, source_id=1, limit=10)

        attachments = self.db.query(Attachment).filter(Attachment.post_id == existing_post.id).all()
        fields = {
            field.field_name: field.field_value
            for field in self.db.query(PostField).filter(PostField.post_id == existing_post.id).all()
        }

        self.assertEqual(result["posts_updated"], 1)
        self.assertEqual(result["attachments_discovered"], 1)
        self.assertEqual(result["attachments_downloaded"], 1)
        self.assertEqual(result["attachments_parsed"], 1)
        self.assertGreaterEqual(result["fields_added"], 3)
        self.assertEqual(len(attachments), 1)
        self.assertTrue(attachments[0].is_downloaded)
        self.assertEqual(fields["学历要求"], "博士")
        self.assertEqual(fields["工作地点"], "无锡")
        jobs = self.db.query(PostJob).filter(PostJob.post_id == existing_post.id).all()
        self.assertEqual(jobs[0].job_name, "专职辅导员")

    async def test_backfill_existing_attachments_should_count_detail_failed_as_failure(self):
        existing_post = Post(
            source_id=1,
            title="历史详情失败公告",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/history-detail-failed",
            original_url="https://example.com/history-detail-failed",
            is_counselor=True,
            confidence_score=0.95,
        )
        self.db.add(existing_post)
        self.db.commit()

        class FailedDetailScraper:
            async def scrape_detail_page(self, url: str):
                return {
                    "content": "",
                    "attachments": [],
                    "detail_failed": True,
                }

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(b"")

        with patch("src.services.scraper_service.create_scraper", return_value=FailedDetailScraper()):
            result = await backfill_existing_attachments(self.db, source_id=1, limit=10)

        saved_post = self.db.query(Post).filter(Post.id == existing_post.id).first()

        self.assertEqual(result["posts_updated"], 0)
        self.assertEqual(result["attachments_discovered"], 0)
        self.assertEqual(result["attachments_downloaded"], 0)
        self.assertEqual(result["attachments_parsed"], 0)
        self.assertEqual(result["failures"], 1)
        self.assertEqual(saved_post.content, "已有正文")

    async def test_backfill_existing_attachments_should_remove_stale_attachments_fields_and_jobs_when_detail_has_no_attachments(self):
        existing_post = Post(
            source_id=1,
            title="历史岗位表已移除公告",
            content="详见附件。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/history-empty-attachments",
            original_url="https://example.com/history-empty-attachments",
            is_counselor=True,
            confidence_score=0.9,
        )
        self.db.add(existing_post)
        self.db.flush()
        attachment_path = self.build_attachment_storage_path(
            existing_post.id,
            "历史岗位表.xlsx",
            "https://example.com/files/history-empty.xlsx",
        )
        attachment_path.write_bytes(build_excel_bytes([
            ["岗位", "人数", "学历", "地点"],
            ["辅导员", "2", "硕士", "南京"],
        ]))
        self.db.add(Attachment(
            post_id=existing_post.id,
            filename="downfile.jsp",
            file_url="https://example.com/files/history-empty.xlsx",
            file_type="",
            is_downloaded=True,
            local_path=str(attachment_path),
            file_size=attachment_path.stat().st_size,
        ))
        self.db.add(PostField(post_id=existing_post.id, field_name="学历要求", field_value="硕士"))
        self.db.add(PostJob(
            post_id=existing_post.id,
            job_name="辅导员",
            recruitment_count="2人",
            source_type="attachment",
            is_counselor=True,
            confidence_score=0.8,
            raw_payload_json=json.dumps({"岗位名称": "辅导员"}, ensure_ascii=False),
            sort_order=0,
        ))
        self.db.commit()

        class HistoryBackfillScraper:
            async def scrape_detail_page(self, url: str):
                return {
                    "content": "详见附件。",
                    "attachments": [],
                    "detail_failed": False,
                }

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(b"")

        with patch("src.services.scraper_service.create_scraper", return_value=HistoryBackfillScraper()):
            result = await backfill_existing_attachments(self.db, source_id=1, limit=10)

        self.assertEqual(result["posts_updated"], 1)
        self.assertEqual(self.db.query(Attachment).filter(Attachment.post_id == existing_post.id).count(), 0)
        self.assertEqual(self.db.query(PostField).filter(PostField.post_id == existing_post.id).count(), 0)
        self.assertEqual(self.db.query(PostJob).filter(PostJob.post_id == existing_post.id).count(), 0)

    async def test_backfill_existing_attachments_should_emit_persisting_progress(self):
        existing_post = Post(
            source_id=1,
            title="历史辅导员公告",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/history-progress",
            original_url="https://example.com/history-progress",
            is_counselor=True,
            confidence_score=0.95
        )
        self.db.add(existing_post)
        self.db.commit()

        attachment_bytes = build_excel_bytes([
            ["岗位名称", "招聘人数", "学历要求", "工作地点"],
            ["专职辅导员", "4", "博士", "无锡"]
        ])
        updates = []

        class HistoryBackfillScraper:
            async def scrape_detail_page(self, url: str):
                return {
                    "content": "已有正文",
                    "attachments": [
                        {
                            "filename": "历史岗位表.xlsx",
                            "file_url": "https://example.com/files/history-progress.xlsx",
                            "file_type": "xlsx"
                        }
                    ]
                }

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(attachment_bytes)

        with patch("src.services.scraper_service.create_scraper", return_value=HistoryBackfillScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ):
            result = await backfill_existing_attachments(
                self.db,
                source_id=1,
                limit=10,
                progress_callback=updates.append,
            )

        self.assertEqual(result["posts_updated"], 1)
        self.assertEqual(updates[-1]["stage"], "persisting")
        self.assertEqual(updates[-1]["stage_key"], "persist-attachments")
        self.assertEqual(updates[-1]["metrics"]["posts_scanned"], 1)
        self.assertEqual(updates[-1]["metrics"]["posts_updated"], 1)

    async def test_backfill_existing_attachments_should_trigger_bundle_without_overwriting_openai_insight(self):
        existing_post = Post(
            source_id=1,
            title="历史 OpenAI 洞察公告",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/history-openai-insight",
            original_url="https://example.com/history-openai-insight",
            is_counselor=True,
            confidence_score=0.95,
        )
        self.db.add(existing_post)
        self.db.flush()
        self.db.add(PostInsight(
            post_id=existing_post.id,
            insight_status="success",
            insight_provider="openai",
            model_name="gpt-5.4",
            prompt_version="v1",
            recruitment_count_total=4,
            counselor_recruitment_count=4,
            degree_floor="博士",
            city_list_json=json.dumps(["无锡"], ensure_ascii=False),
            gender_restriction="不限",
            political_status_required="",
            deadline_text="2026年4月10日",
            deadline_date="2026-04-10",
            deadline_status="报名中",
            has_written_exam=True,
            has_interview=True,
            has_attachment_job_table=True,
            evidence_summary="历史 OpenAI insight",
            raw_result_json="{}",
            analyzed_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        ))
        self.db.commit()

        attachment_bytes = build_excel_bytes([
            ["岗位名称", "招聘人数", "学历要求", "工作地点"],
            ["专职辅导员", "4", "博士", "无锡"]
        ])

        class HistoryBackfillScraper:
            async def scrape_detail_page(self, url: str):
                return {
                    "content": "已有正文",
                    "attachments": [
                        {
                            "filename": "历史岗位表.xlsx",
                            "file_url": "https://example.com/files/history-openai.xlsx",
                            "file_type": "xlsx"
                        }
                    ]
                }

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(attachment_bytes)

        with patch("src.services.scraper_service.create_scraper", return_value=HistoryBackfillScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ), patch(
            "src.services.scraper_service.ensure_rule_analysis_bundle",
            wraps=ensure_rule_analysis_bundle,
        ) as mocked_bundle:
            result = await backfill_existing_attachments(self.db, source_id=1, limit=10)

        saved_insight = self.db.query(PostInsight).filter(PostInsight.post_id == existing_post.id).first()

        self.assertEqual(result["posts_updated"], 1)
        self.assertEqual(mocked_bundle.call_count, 1)
        self.assertEqual(mocked_bundle.call_args.args[1].id, existing_post.id)
        self.assertEqual(saved_insight.insight_provider, "openai")
        self.assertEqual(saved_insight.evidence_summary, "历史 OpenAI insight")

    async def test_backfill_existing_attachments_should_stop_before_next_post_when_cancel_requested(self):
        first_post = Post(
            source_id=1,
            title="历史辅导员公告-1",
            content="已有正文",
            publish_date=datetime(2026, 3, 2, tzinfo=timezone.utc),
            canonical_url="https://example.com/history-cancel-1",
            original_url="https://example.com/history-cancel-1",
            is_counselor=True,
            confidence_score=0.95,
        )
        second_post = Post(
            source_id=1,
            title="历史辅导员公告-2",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/history-cancel-2",
            original_url="https://example.com/history-cancel-2",
            is_counselor=True,
            confidence_score=0.95,
        )
        self.db.add_all([first_post, second_post])
        self.db.commit()

        attachment_bytes = build_excel_bytes([
            ["岗位名称", "招聘人数", "学历要求", "工作地点"],
            ["专职辅导员", "2", "硕士", "南京"],
        ])

        class HistoryBackfillScraper:
            async def scrape_detail_page(self, url: str):
                return {
                    "content": "已有正文",
                    "attachments": [
                        {
                            "filename": "历史岗位表.xlsx",
                            "file_url": f"{url}/history.xlsx",
                            "file_type": "xlsx",
                        }
                    ],
                }

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(attachment_bytes)

        def cancel_check():
            return self.db.query(Attachment).filter(Attachment.post_id == first_post.id).count() > 0

        with patch("src.services.scraper_service.create_scraper", return_value=HistoryBackfillScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path,
        ):
            with self.assertRaises(TaskCancellationRequested):
                await backfill_existing_attachments(
                    self.db,
                    source_id=1,
                    limit=10,
                    cancel_check=cancel_check,
                )

        first_attachments = self.db.query(Attachment).filter(Attachment.post_id == first_post.id).count()
        second_attachments = self.db.query(Attachment).filter(Attachment.post_id == second_post.id).count()

        self.assertEqual(first_attachments, 1)
        self.assertEqual(second_attachments, 0)

    def test_should_refresh_post_attachments_should_ignore_stale_parse_sidecar(self):
        post = Post(
            source_id=1,
            title="历史辅导员公告",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/history-stale",
            original_url="https://example.com/history-stale",
        )
        self.db.add(post)
        self.db.flush()

        attachment_path = Path(self.temp_dir.name) / "history-jobs.xlsx"
        attachment_path.write_bytes(b"fake")
        Path(f"{attachment_path}.fields.json").write_text(
            """{
  "filename": "history-jobs.xlsx",
  "file_type": "xlsx",
  "parser": "table",
  "text_length": 0,
  "fields": [],
  "jobs": []
}""",
            encoding="utf-8"
        )
        attachment = Attachment(
            post_id=post.id,
            filename="history-jobs.xlsx",
            file_url="https://example.com/files/history-jobs.xlsx",
            file_type="xlsx",
            is_downloaded=True,
            local_path=str(attachment_path),
            file_size=4,
        )
        self.db.add(attachment)
        self.db.commit()

        post = self.db.query(Post).filter(Post.id == post.id).first()

        self.assertFalse(should_refresh_post_attachments(post))

    async def test_scrape_and_save_should_parse_pdf_attachment(self):
        class PdfScraper:
            async def scrape(self, max_pages=10, progress_callback=None):
                return [
                    {
                        "title": "PDF 辅导员公告",
                        "url": "https://example.com/pdf-post",
                        "publish_date": datetime(2026, 3, 5, tzinfo=timezone.utc),
                        "content": "",
                        "attachments": [
                            {
                                "filename": "岗位表.pdf",
                                "file_url": "https://example.com/files/jobs.pdf",
                                "file_type": "pdf"
                            }
                        ]
                    }
                ]

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(b"%PDF-1.4 fake")

        fake_pdf_module = SimpleNamespace(
            open=lambda _path: FakePdfDocument([
                FakePdfPage("性别要求：男；学历要求：硕士；专业：思想政治教育；工作地点：南京市；招聘人数：2人")
            ])
        )

        with patch("src.services.scraper_service.create_scraper", return_value=PdfScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ), patch(
            "src.services.attachment_service.pdfplumber",
            fake_pdf_module
        ):
            result = await scrape_and_save(self.db, source_id=1, max_pages=1)

        saved_post = self.db.query(Post).filter(Post.canonical_url == "https://example.com/pdf-post").first()
        fields = {
            field.field_name: field.field_value
            for field in self.db.query(PostField).filter(PostField.post_id == saved_post.id).all()
        }
        attachment = self.db.query(Attachment).filter(Attachment.post_id == saved_post.id).first()

        self.assertEqual(result["processed_records"], 1)
        self.assertIsNotNone(attachment)
        self.assertTrue(attachment.is_downloaded)
        self.assertEqual(fields["学历要求"], "硕士")
        self.assertEqual(fields["工作地点"], "南京市")


if __name__ == "__main__":
    unittest.main()
