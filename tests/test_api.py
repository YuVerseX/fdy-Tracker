import unittest
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api import posts as posts_api
from src.database.models import Attachment, Base, Post, PostAnalysis, PostField, PostJob, Source
from src.services.attachment_service import write_attachment_parse_result


class PostsApiTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test_api.db"
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False}
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        Base.metadata.create_all(bind=self.engine)
        self._seed_data()

        app = FastAPI()
        app.include_router(posts_api.router, prefix="/api")

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[posts_api.get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _seed_data(self):
        db = self.SessionLocal()
        try:
            source = Source(
                id=1,
                name="江苏省人力资源和社会保障厅",
                province="江苏",
                source_type="government_website",
                base_url="http://jshrss.jiangsu.gov.cn/col/col80382/index.html",
                scraper_class="JiangsuHRSSScraper",
                is_active=True
            )
            db.add(source)
            db.flush()

            first_post = Post(
                id=1,
                source_id=source.id,
                title="南京大学专职辅导员招聘公告",
                content="南京大学现招聘专职辅导员，工作地点：南京市",
                publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
                canonical_url="https://example.com/posts/1",
                original_url="https://example.com/posts/1",
                is_counselor=True,
                confidence_score=0.9,
                counselor_scope="dedicated",
                has_counselor_job=True,
            )
            second_post = Post(
                id=2,
                source_id=source.id,
                title="苏州高校行政岗位招聘公告",
                content="",
                publish_date=datetime(2026, 3, 2, tzinfo=timezone.utc),
                canonical_url="https://example.com/posts/2",
                original_url="https://example.com/posts/2",
                is_counselor=False,
                confidence_score=None
            )
            third_post = Post(
                id=3,
                source_id=source.id,
                title="某高校2026年公开招聘专职辅导员及体育教师公告",
                content="本次招聘含专职辅导员岗位和体育教师岗位。",
                publish_date=datetime(2026, 3, 3, tzinfo=timezone.utc),
                canonical_url="https://example.com/posts/3",
                original_url="https://example.com/posts/3",
                is_counselor=True,
                confidence_score=0.65,
                counselor_scope="contains",
                has_counselor_job=True,
            )
            fourth_post = Post(
                id=4,
                source_id=source.id,
                title="某高校2026年公开招聘专职辅导员公告",
                content="岗位表中注明性别不限。",
                publish_date=datetime(2026, 3, 4, tzinfo=timezone.utc),
                canonical_url="https://example.com/posts/4",
                original_url="https://example.com/posts/4",
                is_counselor=True,
                confidence_score=0.8,
                counselor_scope="dedicated",
                has_counselor_job=True,
            )
            fifth_post = Post(
                id=5,
                source_id=source.id,
                title="某高校2025年公开招聘工作人员拟聘用人员名单公示",
                content="根据招聘公告，现将拟聘用人员名单予以公示。",
                publish_date=datetime(2026, 3, 5, tzinfo=timezone.utc),
                canonical_url="https://example.com/posts/5",
                original_url="https://example.com/posts/5",
                is_counselor=False,
                confidence_score=None,
                counselor_scope="none",
                has_counselor_job=False,
            )
            duplicate_post = Post(
                id=99,
                source_id=source.id,
                title="南京大学专职辅导员招聘公告（重复）",
                content="南京大学现招聘专职辅导员，工作地点：南京市",
                publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
                canonical_url="https://example.com/posts/99",
                original_url="https://example.com/posts/99",
                is_counselor=True,
                confidence_score=0.9,
                counselor_scope="dedicated",
                has_counselor_job=True,
                duplicate_status="duplicate",
                duplicate_group_key="duplicate:1:1",
                primary_post_id=1,
                duplicate_reason="source_date_title",
            )
            db.add_all([first_post, second_post, third_post, fourth_post, fifth_post, duplicate_post])
            db.flush()

            db.add_all([
                PostField(post_id=first_post.id, field_name="性别要求", field_value="男"),
                PostField(post_id=first_post.id, field_name="学历要求", field_value="硕士"),
                PostField(post_id=first_post.id, field_name="工作地点", field_value="南京市"),
                PostField(post_id=third_post.id, field_name="学历要求", field_value="本科"),
                PostField(post_id=third_post.id, field_name="工作地点", field_value="苏州"),
                PostField(post_id=fourth_post.id, field_name="学历要求", field_value="本科"),
                PostField(post_id=fifth_post.id, field_name="岗位名称", field_value="C01；C02"),
                PostField(post_id=fifth_post.id, field_name="招聘人数", field_value="1人；2人"),
                PostField(post_id=fifth_post.id, field_name="学历要求", field_value="硕士研究生"),
                PostField(post_id=fifth_post.id, field_name="专业要求", field_value="国际商务；风景园林学"),
                PostField(post_id=fifth_post.id, field_name="工作地点", field_value="南京信息职业技术学院"),
            ])
            local_attachment_path = Path(self.temp_dir.name) / "jobs.xlsx"
            local_attachment_path.write_bytes(b"fake-excel-content")
            write_attachment_parse_result(
                local_attachment_path,
                {
                    "filename": "岗位表.xlsx",
                    "file_type": "xlsx",
                    "fields": [
                        {"field_name": "学历要求", "field_value": "硕士"}
                    ],
                    "jobs": [],
                }
            )
            db.add(Attachment(
                post_id=first_post.id,
                filename="岗位表.xlsx",
                file_url="https://example.com/files/jobs.xlsx",
                file_type="xlsx",
                is_downloaded=True,
                local_path=str(local_attachment_path),
                file_size=1024
            ))
            db.add(PostJob(
                post_id=first_post.id,
                job_name="专职辅导员",
                recruitment_count="2人",
                education_requirement="硕士",
                major_requirement="思想政治教育",
                location="南京市",
                source_type="attachment",
                is_counselor=True,
                confidence_score=0.9,
                raw_payload_json=json.dumps({"岗位名称": "专职辅导员"}, ensure_ascii=False),
                sort_order=0,
            ))
            db.add(PostJob(
                post_id=first_post.id,
                job_name="专职辅导员；专职辅导员（男）；专职辅导员（女）",
                recruitment_count="8人；4人；3人",
                education_requirement="硕士；硕士；硕士",
                location="南京市；南京市；南京市",
                source_type="field",
                is_counselor=True,
                confidence_score=0.65,
                raw_payload_json=json.dumps(
                    {
                        "岗位名称": "专职辅导员；专职辅导员（男）；专职辅导员（女）",
                        "招聘人数": "8人；4人；3人",
                    },
                    ensure_ascii=False
                ),
                sort_order=9,
            ))
            db.add(PostJob(
                post_id=third_post.id,
                job_name="专职辅导员（男）",
                recruitment_count="1人",
                education_requirement="硕士研究生及以上",
                major_requirement="思想政治教育",
                location="苏州",
                source_type="attachment",
                is_counselor=True,
                confidence_score=0.88,
                raw_payload_json=json.dumps(
                    {"岗位名称": "专职辅导员（男）", "学历要求": "硕士研究生及以上"},
                    ensure_ascii=False
                ),
                sort_order=0,
            ))
            db.add(PostJob(
                post_id=fourth_post.id,
                job_name="专职辅导员",
                recruitment_count="2人",
                education_requirement="本科及以上",
                major_requirement="思想政治教育",
                location="无锡",
                source_type="attachment",
                is_counselor=True,
                confidence_score=0.8,
                raw_payload_json=json.dumps(
                    {"岗位名称": "专职辅导员", "性别要求": "男女不限"},
                    ensure_ascii=False
                ),
                sort_order=0,
            ))
            db.add(PostJob(
                post_id=fifth_post.id,
                job_name="专职辅导员",
                recruitment_count="2人",
                education_requirement="硕士研究生",
                major_requirement="国际商务；风景园林学",
                location="南京信息职业技术学院",
                source_type="field",
                is_counselor=True,
                confidence_score=0.65,
                raw_payload_json=json.dumps(
                    {
                        "岗位名称": "C01；C02",
                        "学历要求": "硕士研究生",
                        "工作地点": "南京信息职业技术学院",
                    },
                    ensure_ascii=False
                ),
                sort_order=0,
            ))
            db.add(PostAnalysis(
                post_id=first_post.id,
                analysis_status="success",
                analysis_provider="rule",
                model_name="rule-based",
                prompt_version="v1",
                event_type="招聘公告",
                recruitment_stage="招聘启动",
                tracking_priority="high",
                school_name="南京大学",
                city="南京",
                should_track=True,
                summary="这条信息归类为招聘公告。",
                tags_json=json.dumps(["招聘公告", "辅导员相关"], ensure_ascii=False),
                entities_json=json.dumps(["南京大学", "南京"], ensure_ascii=False),
                raw_result_json=json.dumps({"event_type": "招聘公告"}, ensure_ascii=False),
                analyzed_at=datetime(2026, 3, 2, tzinfo=timezone.utc)
            ))
            db.add(PostAnalysis(
                post_id=fifth_post.id,
                analysis_status="success",
                analysis_provider="rule",
                model_name="rule-based",
                prompt_version="v1",
                event_type="结果公示",
                recruitment_stage="结果公示",
                tracking_priority="low",
                school_name="某高校",
                city="南京",
                should_track=False,
                summary="这条信息归类为结果公示。",
                tags_json=json.dumps(["结果公示"], ensure_ascii=False),
                entities_json=json.dumps(["某高校", "南京"], ensure_ascii=False),
                raw_result_json=json.dumps({"event_type": "结果公示"}, ensure_ascii=False),
                analyzed_at=datetime(2026, 3, 5, tzinfo=timezone.utc)
            ))
            db.commit()
        finally:
            db.close()

    def test_get_posts_supports_search(self):
        response = self.client.get("/api/posts", params={"search": "南京大学"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["title"], "南京大学专职辅导员招聘公告")

    def test_get_posts_supports_structured_filters(self):
        response = self.client.get(
            "/api/posts",
            params={"gender": "男", "has_content": "true"}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        returned_ids = {item["id"] for item in payload["items"]}
        self.assertEqual(payload["total"], 2)
        self.assertEqual(returned_ids, {1, 3})
        self.assertTrue(all(item["has_content"] for item in payload["items"]))

    def test_get_posts_should_support_gender_filter_from_job_name(self):
        response = self.client.get(
            "/api/posts",
            params={"gender": "男"}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        returned_ids = {item["id"] for item in payload["items"]}
        self.assertIn(1, returned_ids)
        self.assertIn(3, returned_ids)

    def test_get_posts_should_support_unlimited_gender_from_job_payload(self):
        response = self.client.get(
            "/api/posts",
            params={"gender": "不限"}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        returned_ids = {item["id"] for item in payload["items"]}
        self.assertIn(4, returned_ids)

    def test_get_posts_should_support_education_filter_from_post_jobs(self):
        response = self.client.get(
            "/api/posts",
            params={"education": "硕士"}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        returned_ids = {item["id"] for item in payload["items"]}
        self.assertIn(1, returned_ids)
        self.assertIn(3, returned_ids)

    def test_get_posts_should_support_location_filter_from_post_jobs(self):
        response = self.client.get(
            "/api/posts",
            params={"location": "苏州"}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        returned_ids = {item["id"] for item in payload["items"]}
        self.assertIn(3, returned_ids)

    def test_get_posts_should_skip_result_notice_dirty_education_match(self):
        response = self.client.get(
            "/api/posts",
            params={"education": "硕士"}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        returned_ids = {item["id"] for item in payload["items"]}
        self.assertNotIn(5, returned_ids)

    def test_get_posts_should_skip_result_notice_dirty_location_match(self):
        response = self.client.get(
            "/api/posts",
            params={"location": "南京"}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        returned_ids = {item["id"] for item in payload["items"]}
        self.assertNotIn(5, returned_ids)

    def test_get_posts_supports_event_type_filter(self):
        response = self.client.get(
            "/api/posts",
            params={"event_type": "招聘公告"}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["analysis"]["event_type"], "招聘公告")

    def test_get_posts_supports_counselor_scope_filter(self):
        response = self.client.get(
            "/api/posts",
            params={"counselor_scope": "dedicated", "has_counselor_job": "true"}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        returned_ids = {item["id"] for item in payload["items"]}
        self.assertEqual(payload["total"], 2)
        self.assertEqual(returned_ids, {1, 4})
        self.assertTrue(all(item["counselor_scope"] == "dedicated" for item in payload["items"]))
        self.assertTrue(all(item["has_counselor_job"] for item in payload["items"]))
        self.assertTrue(all(item["jobs_count"] == 1 for item in payload["items"]))
        self.assertEqual(payload["items"][0]["job_snapshot"]["job_name"], "专职辅导员")

    def test_get_posts_should_support_contains_scope_filter(self):
        response = self.client.get(
            "/api/posts",
            params={"counselor_scope": "contains", "has_counselor_job": "true"}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["id"], 3)
        self.assertEqual(payload["items"][0]["counselor_scope"], "contains")

    def test_get_posts_should_include_title_derived_counselor_post_in_counselor_filter(self):
        db = self.SessionLocal()
        try:
            db.add(Post(
                id=777,
                source_id=1,
                title="东南大学2026年公开招聘专职辅导员公告",
                content="这是一个历史兼容脏数据样例。",
                publish_date=datetime(2026, 3, 6, tzinfo=timezone.utc),
                canonical_url="https://example.com/posts/777",
                original_url="https://example.com/posts/777",
                is_counselor=False,
                counselor_scope="",
                has_counselor_job=False,
                confidence_score=None,
            ))
            db.commit()
        finally:
            db.close()

        params = {"is_counselor": "true"}
        list_response = self.client.get("/api/posts", params=params)
        summary_response = self.client.get("/api/posts/stats/summary", params=params)

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(summary_response.status_code, 200)

        list_payload = list_response.json()
        summary_payload = summary_response.json()
        returned_ids = {item["id"] for item in list_payload["items"]}
        derived_item = next(item for item in list_payload["items"] if item["id"] == 777)

        self.assertIn(777, returned_ids)
        self.assertEqual(list_payload["total"], 4)
        self.assertTrue(derived_item["is_counselor"])
        self.assertEqual(derived_item["counselor_scope"], "dedicated")
        self.assertTrue(derived_item["has_counselor_job"])
        self.assertEqual(summary_payload["overview"]["total_posts"], 4)
        self.assertEqual(summary_payload["overview"]["counselor_posts"], 4)

    def test_get_posts_should_include_null_flag_post_in_negative_counselor_filters(self):
        db = self.SessionLocal()
        try:
            db.add(Post(
                id=778,
                source_id=1,
                title="苏州高校后勤岗位招聘公告",
                content="这是一个非辅导员历史空值样例。",
                publish_date=datetime(2026, 3, 6, tzinfo=timezone.utc),
                canonical_url="https://example.com/posts/778",
                original_url="https://example.com/posts/778",
                is_counselor=None,
                counselor_scope=None,
                has_counselor_job=None,
                confidence_score=None,
            ))
            db.commit()
        finally:
            db.close()

        params = {
            "is_counselor": "false",
            "counselor_scope": "none",
            "has_counselor_job": "false",
        }
        list_response = self.client.get("/api/posts", params=params)
        summary_response = self.client.get("/api/posts/stats/summary", params=params)

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(summary_response.status_code, 200)

        list_payload = list_response.json()
        summary_payload = summary_response.json()
        returned_ids = {item["id"] for item in list_payload["items"]}
        null_flag_item = next(item for item in list_payload["items"] if item["id"] == 778)

        self.assertIn(778, returned_ids)
        self.assertEqual(list_payload["total"], 3)
        self.assertFalse(null_flag_item["is_counselor"])
        self.assertEqual(null_flag_item["counselor_scope"], "none")
        self.assertFalse(null_flag_item["has_counselor_job"])
        self.assertEqual(summary_payload["overview"]["total_posts"], 3)
        self.assertEqual(summary_payload["overview"]["counselor_posts"], 0)

    def test_get_post_detail_returns_nested_source(self):
        response = self.client.get("/api/posts/1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source"]["name"], "江苏省人力资源和社会保障厅")
        self.assertEqual(payload["fields"][0]["field_name"], "性别要求")
        self.assertEqual(payload["attachments"][0]["filename"], "岗位表.xlsx")
        self.assertEqual(payload["analysis"]["event_type"], "招聘公告")
        self.assertEqual(payload["counselor_scope"], "dedicated")
        self.assertTrue(payload["has_counselor_job"])
        self.assertEqual(payload["jobs_count"], 1)
        self.assertEqual(payload["job_items"][0]["job_name"], "专职辅导员")

    def test_get_posts_should_hide_duplicate_records_by_default(self):
        response = self.client.get("/api/posts")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = {item["id"] for item in payload["items"]}
        self.assertNotIn(99, ids)

    def test_get_post_detail_should_resolve_duplicate_record_to_primary(self):
        response = self.client.get("/api/posts/99")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], 1)
        self.assertEqual(payload["canonical_url"], "https://example.com/posts/1")

    def test_get_post_detail_returns_attachments(self):
        response = self.client.get("/api/posts/1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["attachments"]), 1)
        self.assertEqual(payload["attachments"][0]["file_type"], "xlsx")
        self.assertEqual(payload["attachments"][0]["parse_status"], "已解析")
        self.assertEqual(payload["attachments"][0]["parsed_fields_count"], 1)

    def test_get_post_detail_should_hide_result_notice_dirty_fields(self):
        response = self.client.get("/api/posts/5")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        field_names = {field["field_name"] for field in payload["fields"]}
        self.assertEqual(payload["analysis"]["event_type"], "结果公示")
        self.assertNotIn("岗位名称", field_names)
        self.assertNotIn("招聘人数", field_names)
        self.assertNotIn("学历要求", field_names)
        self.assertNotIn("专业要求", field_names)
        self.assertNotIn("工作地点", field_names)

    def test_get_post_detail_should_deduplicate_repeated_fields(self):
        db = self.SessionLocal()
        try:
            db.add(PostField(post_id=1, field_name="学历要求", field_value="硕士"))
            db.commit()
        finally:
            db.close()

        response = self.client.get("/api/posts/1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        education_fields = [
            field for field in payload["fields"]
            if field["field_name"] == "学历要求" and field["field_value"] == "硕士"
        ]
        self.assertEqual(len(education_fields), 1)

    def test_format_post_content_should_split_attachment_signature(self):
        content = (
            "苏州大学附属第一医院2026年博士专项招聘拟聘用人员名单公示"
            "发布日期： 2026-03-17"
            "根据公告内容进行公示。"
            "\n\n附件：苏州大学附属第一医院2026年博士专项招聘拟聘用人员名单"
            "苏州大学附属第一医院2026年3月17日"
            "\n\n附件：苏州大学附属第一医院2026年博士专项招聘拟聘用人员名单.xls"
        )

        formatted = posts_api.format_post_content(
            "苏州大学附属第一医院2026年博士专项招聘拟聘用人员名单公示",
            content
        )

        self.assertTrue(formatted.startswith("根据公告内容进行公示。"))
        self.assertIn(
            "附件：苏州大学附属第一医院2026年博士专项招聘拟聘用人员名单\n苏州大学附属第一医院\n2026年3月17日",
            formatted
        )

    def test_format_post_content_should_split_heading_and_attachment_tail(self):
        content = (
            "江苏护理职业学院2026年公开招聘工作人员公告"
            "五、公示与聘用对公示无异议人员，经备案后办理聘用手续。"
            "\n\n六、招聘政策咨询江苏护理职业学院人事处负责回答此次招聘政策咨询。"
            "\n\n附件：3.江苏护理职业学院2026年公开招聘工作人员岗位表三"
            "江苏护理职业学院2026年1月29日江苏护理职业学院2026年公开招聘工作人员岗位表一.xls"
        )

        formatted = posts_api.format_post_content(
            "江苏护理职业学院2026年公开招聘工作人员公告",
            content
        )

        self.assertIn("五、公示与聘用\n对公示无异议人员，经备案后办理聘用手续。", formatted)
        self.assertIn("六、招聘政策咨询\n江苏护理职业学院人事处负责回答此次招聘政策咨询。", formatted)
        self.assertIn(
            "3.江苏护理职业学院2026年公开招聘工作人员岗位表三\n江苏护理职业学院\n2026年1月29日\n江苏护理职业学院2026年公开招聘工作人员岗位表一.xls",
            formatted
        )

    def test_format_post_content_should_split_inline_signature_and_attachment_filename(self):
        content = (
            "常州信息职业技术学院2025年公开招聘高层次人才拟聘用人员名单公示（第7次）"
            "根据公告要求，现面向社会进行公示。"
            "\n\n举报电话：0519-86338998（常信）；025-69652969（省工信厅）；025-83230723（省人社厅）。 "
            "常州信息职业技术学院 2026年3月24日"
            "\n 常州信息职业技术学院2025年公开招聘高层次人才拟聘用人员名单公示（第7次）公示人员名单.xls"
        )

        formatted = posts_api.format_post_content(
            "常州信息职业技术学院2025年公开招聘高层次人才拟聘用人员名单公示（第7次）",
            content
        )

        self.assertIn(
            "举报电话：0519-86338998（常信）；025-69652969（省工信厅）；025-83230723（省人社厅）。\n常州信息职业技术学院\n2026年3月24日\n常州信息职业技术学院2025年公开招聘高层次人才拟聘用人员名单公示（第7次）公示人员名单.xls",
            formatted
        )

    def test_format_post_content_should_split_recruitment_plan_heading_with_inline_space(self):
        content = (
            "江苏省中国科学院植物研究所2025年公开招聘专业技术人员公告"
            "一、招聘计划本次公开招聘专业技术人员6名。"
            "\n\n三、报名"
            "\n\n（一）报名时间、地点、方式 应聘人员通过平台报名。"
        )

        formatted = posts_api.format_post_content(
            "江苏省中国科学院植物研究所2025年公开招聘专业技术人员公告",
            content
        )

        self.assertIn("一、招聘计划\n本次公开招聘专业技术人员6名。", formatted)
        self.assertIn("（一）报名时间、地点、方式\n应聘人员通过平台报名。", formatted)

    def test_format_post_content_should_remove_repeated_body_and_x_noise(self):
        content = (
            "南京师范大学2026年公开招聘专职辅导员公告"
            "南京师范大学是省教育厅主管的全额拨款事业单位，位于南京市栖霞区文苑路1号。"
            "为更好地选拔优秀适岗人才，充实人才队伍。"
            "\n\n一、报考条件"
            "\n\n（二）需要满足条件。"
            "\n\n岗位表.xls"
            "\n\nx"
            "\n\n南京师范大学是省教育厅主管的全额拨款事业单位，位于南京市栖霞区文苑路1号。"
            "为更好地选拔优秀适岗人才，充实人才队伍。"
            "\n\n一、报考条件"
            "\n\n（二）需要满足条件。"
            "\n\n后面重复的内容不该再出现。"
        )

        formatted = posts_api.format_post_content(
            "南京师范大学2026年公开招聘专职辅导员公告",
            content
        )

        self.assertEqual(
            formatted.count("南京师范大学是省教育厅主管的全额拨款事业单位"),
            1
        )
        self.assertNotIn("\nx\n", f"\n{formatted}\n")
        self.assertNotIn("后面重复的内容不该再出现。", formatted)

    def test_get_post_detail_returns_404_for_missing_post(self):
        response = self.client.get("/api/posts/999")

        self.assertEqual(response.status_code, 404)

    def test_get_posts_summary_returns_overview(self):
        response = self.client.get("/api/posts/stats/summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["overview"]["total_posts"], 5)
        self.assertEqual(payload["overview"]["counselor_posts"], 3)
        self.assertEqual(payload["overview"]["dedicated_counselor_posts"], 2)
        self.assertEqual(payload["overview"]["contains_counselor_posts"], 1)
        self.assertEqual(payload["overview"]["analyzed_posts"], 2)
        self.assertEqual(payload["overview"]["attachment_posts"], 1)
        self.assertEqual(payload["overview"]["posts_with_jobs"], 3)
        self.assertEqual(payload["overview"]["total_jobs"], 3)
        distribution = {
            item["event_type"]: item["count"]
            for item in payload["event_type_distribution"]
        }
        self.assertEqual(distribution["招聘公告"], 1)
        self.assertEqual(distribution["结果公示"], 1)
        self.assertEqual(payload["days"], 7)
        self.assertEqual(payload["new_in_days"], 0)
        self.assertAlmostEqual(payload["attachment_ratio"], 0.2)

    def test_get_posts_summary_should_support_same_filters_as_list(self):
        response = self.client.get(
            "/api/posts/stats/summary",
            params={"is_counselor": "true", "search": "南京大学"}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["overview"]["total_posts"], 1)
        self.assertEqual(payload["overview"]["counselor_posts"], 1)
        distribution = {
            item["event_type"]: item["count"]
            for item in payload["event_type_distribution"]
        }
        self.assertEqual(distribution["招聘公告"], 1)

    def test_get_posts_and_summary_should_stay_consistent_under_combined_filters(self):
        params = {
            "event_type": "招聘公告",
            "counselor_scope": "dedicated",
            "has_counselor_job": "true",
        }

        list_response = self.client.get("/api/posts", params=params)
        summary_response = self.client.get("/api/posts/stats/summary", params=params)

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(summary_response.status_code, 200)

        list_payload = list_response.json()
        summary_payload = summary_response.json()

        self.assertEqual(list_payload["total"], 1)
        self.assertEqual(list_payload["items"][0]["id"], 1)
        self.assertEqual(summary_payload["overview"]["total_posts"], 1)
        self.assertEqual(summary_payload["overview"]["counselor_posts"], 1)
        distribution = {
            item["event_type"]: item["count"]
            for item in summary_payload["event_type_distribution"]
        }
        self.assertEqual(distribution["招聘公告"], 1)


if __name__ == "__main__":
    unittest.main()
