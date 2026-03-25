import unittest

from src.services.filter_service import is_counselor_position


class FilterServiceTestCase(unittest.TestCase):
    def test_title_hit_should_not_be_killed_by_experience_exclude_words(self):
        matched, confidence = is_counselor_position(
            "南京医科大学2026年公开招聘专职辅导员公告（第一批）",
            "高校辅导员工作经历须真实有效，不含个人学生时期实习、兼职工作经历。"
        )

        self.assertTrue(matched)
        self.assertEqual(confidence, 1.0)

    def test_excluded_role_in_title_should_return_false(self):
        matched, confidence = is_counselor_position(
            "某高校2026年公开招聘兼职辅导员公告",
            "现面向社会公开招聘兼职辅导员。"
        )

        self.assertFalse(matched)
        self.assertEqual(confidence, 0.0)

    def test_content_with_role_context_should_return_false(self):
        matched, confidence = is_counselor_position(
            "江苏护理职业学院2026年公开招聘工作人员公告",
            "报考辅导员岗位须为中共党员，并具备主要学生干部经历。"
        )

        self.assertFalse(matched)
        self.assertEqual(confidence, 0.0)

    def test_content_with_explicit_recruitment_context_should_return_true(self):
        matched, confidence = is_counselor_position(
            "某高校2026年公开招聘工作人员公告",
            "根据工作需要，现面向社会公开招聘专职辅导员2名。"
        )

        self.assertTrue(matched)
        self.assertGreaterEqual(confidence, 0.6)

    def test_plain_counselor_experience_text_should_not_return_true(self):
        matched, confidence = is_counselor_position(
            "某高校公开招聘工作人员公告",
            "应聘人员需具备1年及以上高校辅导员工作经历。"
        )

        self.assertFalse(matched)
        self.assertEqual(confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
