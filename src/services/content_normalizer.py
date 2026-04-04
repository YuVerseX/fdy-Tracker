"""正文清洗共享逻辑。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

JIANGSU_HRSS_CONTENT_PROFILE = "jiangsu_hrss"


@dataclass(frozen=True)
class ContentNormalizationRules:
    noise_texts: frozenset[str]
    noise_prefixes: tuple[str, ...]


CONTENT_NORMALIZATION_RULES = {
    JIANGSU_HRSS_CONTENT_PROFILE: ContentNormalizationRules(
        noise_texts=frozenset({
            "当前位置：",
            "首页",
            "资讯中心",
            "省属事业单位招聘",
            "来源：",
            "发布日期：",
            "点击量：",
            "点击查看原文件：",
            "关闭本页",
            "打印本页",
            "小",
            "中",
            "大",
            ">",
            "[",
            "]",
            "关闭本页打印本页",
        }),
        noise_prefixes=("当前位置：", "发布日期：", "来源：", "字体：["),
    ),
}
SCRAPER_CLASS_CONTENT_PROFILES = {
    "JiangsuHRSSScraper": JIANGSU_HRSS_CONTENT_PROFILE,
}
PROFILE_INLINE_NOISE_TOKENS = {
    JIANGSU_HRSS_CONTENT_PROFILE: (
        "点击查看原文件：",
        "关闭本页打印本页",
    ),
}

ATTACHMENT_SUFFIXES = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar")
ATTACHMENT_SUFFIX_PATTERN = "|".join(re.escape(suffix) for suffix in ATTACHMENT_SUFFIXES)


def resolve_content_profile(source: Any | None = None, scraper_class: str | None = None) -> str | None:
    """根据 source/scraper 元数据解析正文清洗 profile。"""
    if scraper_class:
        normalized_scraper_class = str(scraper_class).strip()
        if normalized_scraper_class:
            return SCRAPER_CLASS_CONTENT_PROFILES.get(normalized_scraper_class)

    source_scraper_class = getattr(source, "scraper_class", None)
    if source_scraper_class:
        return SCRAPER_CLASS_CONTENT_PROFILES.get(str(source_scraper_class).strip())

    return None


def is_noise_text(text: str, *, profile: str | None = None) -> bool:
    """判断是否为正文噪音。"""
    normalized = text.strip()
    if not normalized:
        return True

    rules = CONTENT_NORMALIZATION_RULES.get((profile or "").strip())
    if not rules:
        return False

    if normalized in rules.noise_texts:
        return True

    if any(normalized.startswith(prefix) for prefix in rules.noise_prefixes):
        return True

    return False


def normalize_content_text_for_source(
    content: str,
    *,
    source: Any | None = None,
    scraper_class: str | None = None,
) -> str:
    """按 source profile 执行正文清洗。"""
    return normalize_content_text(
        content,
        profile=resolve_content_profile(source=source, scraper_class=scraper_class),
    )


def normalize_content_text(content: str, *, profile: str | None = None) -> str:
    """清理正文文本，兼容历史脏数据。"""
    if not content:
        return ""

    normalized = content.replace("\r", "\n").replace("\xa0", " ").replace("\u3000", " ")
    raw_lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    filtered_lines = [line for line in raw_lines if not is_noise_text(line, profile=profile)]

    if not filtered_lines:
        return ""

    fragmented_line_count = sum(len(line) <= 6 for line in filtered_lines)
    looks_fragmented = len(filtered_lines) >= 8 and fragmented_line_count / len(filtered_lines) > 0.35

    if looks_fragmented:
        normalized = "".join(filtered_lines)
        for token in PROFILE_INLINE_NOISE_TOKENS.get((profile or "").strip(), ()):
            normalized = normalized.replace(token, "")
    else:
        normalized = "\n\n".join(filtered_lines)

    normalized = re.sub(r"(?<!\n\n)(附件[:：])", r"\n\n\1", normalized)
    normalized = re.sub(
        r"(?<!\n)(举报电话[:：]|咨询电话[:：]|监督电话[:：]|举报信箱[:：]|联系电话[:：])",
        r"\n\1",
        normalized,
    )
    normalized = re.sub(r"(?<!\n\n)([一二三四五六七八九十]+、)", r"\n\n\1", normalized)
    normalized = re.sub(r"(?<!\n)(（[一二三四五六七八九十]+）)", r"\n\1", normalized)
    normalized = re.sub(r"(?<!\d)(?<!\n)([1-9][0-9]?[.、])(?=[^\d])", r"\n\1", normalized)
    normalized = re.sub(r"([0-9-]{7,})([1-9])(?=\.[\u4e00-\u9fff])", r"\1\n\2", normalized)
    normalized = re.sub(
        rf"({ATTACHMENT_SUFFIX_PATTERN})(?=(?:附件[:：]|[\u4e00-\u9fffA-Za-z]))",
        r"\1\n",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()
