import unittest

from src.services.content_normalizer import normalize_content_text


class ContentNormalizerTestCase(unittest.TestCase):
    def test_normalize_content_text_should_not_strip_jiangsu_navigation_noise_without_profile(self):
        content = """
        首页
        资讯中心
        招聘公告正文
        """

        normalized = normalize_content_text(content)

        self.assertIn("首页", normalized)
        self.assertIn("资讯中心", normalized)
        self.assertIn("招聘公告正文", normalized)

    def test_normalize_content_text_should_not_strip_jiangsu_inline_tokens_without_profile(self):
        content = """
        点击查看原文件：
        关
        闭
        本
        页
        打
        印
        本
        页
        招
        聘
        公
        告
        正
        文
        """

        normalized = normalize_content_text(content)

        self.assertIn("点击查看原文件：", normalized)
        self.assertIn("关闭本页打印本页", normalized)
        self.assertIn("招聘公告正文", normalized)


if __name__ == "__main__":
    unittest.main()
