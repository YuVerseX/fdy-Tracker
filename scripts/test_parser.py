"""解析器测试脚本"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers.post_parser import PostParser, parse_post_fields
from loguru import logger


def test_parser():
    """测试招聘信息解析器"""
    logger.info("=" * 50)
    logger.info("开始测试招聘信息解析器")
    logger.info("=" * 50)

    # 测试样例
    test_cases = [
        {
            "title": "江苏某大学招聘专职辅导员公告",
            "content": """
            一、招聘岗位
            专职辅导员 5人

            二、岗位要求
            1. 性别：不限
            2. 学历：硕士研究生及以上学历
            3. 专业：思想政治教育、教育学、心理学等相关专业
            4. 年龄：30周岁以下
            5. 政治面貌：中共党员
            6. 工作地点：南京市

            三、报名时间
            报名时间：2024年1月1日至2024年1月15日
            """
        },
        {
            "title": "2024年高校辅导员招聘",
            "content": """
            招聘人数：3名
            性别要求：男
            学历要求：本科及以上
            专业：不限
            年龄：35岁以下
            工作地点：苏州市
            """
        },
        {
            "title": "某学院招聘公告",
            "content": """
            岗位：专职辅导员
            要求：
            - 博士学位
            - 女性优先
            - 思想政治教育专业
            - 党员
            - 工作地点：无锡市
            招聘2人
            """
        }
    ]

    parser = PostParser()

    for i, test_case in enumerate(test_cases, 1):
        logger.info(f"\n{'=' * 50}")
        logger.info(f"测试案例 {i}: {test_case['title']}")
        logger.info(f"{'=' * 50}")

        # 解析字段
        fields = parser.parse(test_case['title'], test_case['content'])

        # 输出结果
        logger.info("\n解析结果:")
        for field_name, field_value in fields.items():
            if field_value:
                logger.success(f"  ✓ {field_name}: {field_value}")
            else:
                logger.warning(f"  ✗ {field_name}: 未提取")

        # 测试 parse_post_fields 函数
        logger.info("\n结构化字段列表:")
        fields_list = parse_post_fields(test_case['title'], test_case['content'])
        for field in fields_list:
            logger.info(f"  - {field['field_name']}: {field['field_value']}")

    logger.info("\n" + "=" * 50)
    logger.info("测试完成")
    logger.info("=" * 50)


if __name__ == "__main__":
    test_parser()
