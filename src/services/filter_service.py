"""过滤服务"""
import re
from typing import Iterable, Tuple
from loguru import logger


ROLE_EXCLUDE_PATTERNS = (
    r"兼职\s*辅导员",
    r"临时\s*辅导员",
    r"实习\s*辅导员",
    r"辅导员\s*兼职",
    r"辅导员\s*临时",
    r"辅导员\s*实习",
)

CONTENT_INCLUDE_PATTERNS = (
    r"(?:公开招聘|招聘|招录|招考).{0,10}(?:专职)?(?:[\u4e00-\u9fff]{0,8})?辅导员",
    r"(?:拟聘用|拟录用|聘用).{0,10}(?:专职)?(?:[\u4e00-\u9fff]{0,8})?辅导员",
    r"(?:专职)?(?:[\u4e00-\u9fff]{0,8})?辅导员.{0,10}(?:公告|招聘|招录|招考|拟聘用|拟录用)",
)

CONTENT_EXCLUDE_PATTERNS = (
    r"(?:报考|应聘|符合|具备|从事|担任|须为|需有|具有).{0,12}(?:专职)?(?:[\u4e00-\u9fff]{0,8})?辅导员(?:岗位|岗|工作)?",
    r"(?:专职)?(?:[\u4e00-\u9fff]{0,8})?辅导员(?:岗位|岗|工作)?.{0,12}(?:须|需|应|限|条件|经历)",
)


def _matches_any_pattern(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def is_counselor_position(title: str, content: str = "") -> Tuple[bool, float]:
    """
    判断是否为专职辅导员岗位

    Args:
        title: 标题
        content: 正文内容

    Returns:
        Tuple[bool, float]: (是否匹配, 置信度分数)
    """
    title_text = (title or "").lower()
    content_text = (content or "").lower()

    if _matches_any_pattern(title_text, ROLE_EXCLUDE_PATTERNS):
        logger.debug("标题命中排除角色词，不匹配")
        return False, 0.0

    if "专职辅导员" in title_text:
        logger.debug("标题命中'专职辅导员'，判定为匹配")
        return True, 1.0

    if "辅导员" in title_text:
        logger.debug("标题命中'辅导员'，判定为匹配")
        return True, 0.8

    if _matches_any_pattern(content_text, ROLE_EXCLUDE_PATTERNS):
        logger.debug("正文命中排除角色词，不匹配")
        return False, 0.0

    if _matches_any_pattern(content_text, CONTENT_EXCLUDE_PATTERNS):
        logger.debug("正文只命中条件/经历语境，不匹配")
        return False, 0.0

    if _matches_any_pattern(content_text, CONTENT_INCLUDE_PATTERNS):
        confidence = 0.8 if "专职辅导员" in content_text else 0.6
        logger.debug(f"正文命中岗位语境，置信度: {confidence:.2f}")
        return True, confidence

    logger.debug("未命中辅导员岗位规则")
    return False, 0.0
