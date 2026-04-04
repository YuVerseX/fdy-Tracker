"""江苏省人社厅爬虫"""
from pathlib import Path
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from loguru import logger
from src.scrapers.base import BaseScraper
from src.services.content_normalizer import (
    ATTACHMENT_SUFFIXES,
    ATTACHMENT_SUFFIX_PATTERN,
    JIANGSU_HRSS_CONTENT_PROFILE,
    is_noise_text as is_generic_noise_text,
    normalize_content_text as normalize_generic_content_text,
)
from src.services.task_progress import ProgressCallback, emit_progress
GENERIC_ATTACHMENT_TEXTS = {"附件", "下载", "点击下载", "查看附件", "点击查看原文件"}
DEFAULT_BASE_URL = "https://jshrss.jiangsu.gov.cn/col/col80382/index.html"
DEFAULT_AJAX_PATH = "/module/web/jpage/dataproxy.jsp"
DEFAULT_AJAX_PARAMS = {
    "columnid": "80382",
    "unitid": "325517",
    "webid": "67",
}
DETAIL_ERROR_MARKERS = (
    "404 not found",
    "nginx 404",
    "error 404",
    "页面不存在",
    "您访问的页面不存在",
    "系统发生错误",
    "访问出错",
)


def normalize_content_text(content: str) -> str:
    """江苏源正文清洗始终使用本源 profile。"""
    return normalize_generic_content_text(content, profile=JIANGSU_HRSS_CONTENT_PROFILE)


def is_noise_text(text: str) -> bool:
    """江苏源噪音识别。"""
    return is_generic_noise_text(text, profile=JIANGSU_HRSS_CONTENT_PROFILE)


def build_site_root(base_url: str) -> str:
    """从入口地址推导站点根域名。"""
    parsed = urlparse((base_url or "").strip() or DEFAULT_BASE_URL)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"

    fallback = urlparse(DEFAULT_BASE_URL)
    return f"{fallback.scheme}://{fallback.netloc}"


def build_ajax_params(
    base_url: str,
    overrides: Dict[str, str] | None = None,
) -> Dict[str, str]:
    """从 source base_url 推导列表翻页所需参数。"""
    effective_base_url = (base_url or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    params: Dict[str, str] = {}
    parsed = urlparse(effective_base_url)
    query = parse_qs(parsed.query)

    match = re.search(r"/col/col(\d+)", parsed.path or "")
    if match:
        params["columnid"] = match.group(1)

    for key in ("columnid", "unitid", "webid"):
        values = query.get(key)
        if values and values[0]:
            params[key] = values[0]

    for key, value in (overrides or {}).items():
        if value:
            params[key] = value

    missing = [key for key in ("columnid", "unitid", "webid") if not params.get(key)]
    if missing:
        default_parsed = urlparse(DEFAULT_BASE_URL)
        is_legacy_default_source = (
            parsed.netloc == default_parsed.netloc
            and parsed.path == default_parsed.path
            and params.get("columnid") == DEFAULT_AJAX_PARAMS["columnid"]
        )
        if is_legacy_default_source:
            for key in missing:
                params[key] = DEFAULT_AJAX_PARAMS[key]
        else:
            missing_params = ", ".join(missing)
            raise ValueError(f"source base_url 缺少必要的 Ajax 参数: {missing_params}")

    return params


def infer_attachment_type(filename: str, file_url: str) -> str:
    """根据文件名或链接推断附件类型"""
    candidates = [
        (filename or "").lower(),
        extract_filename_from_url(file_url).lower(),
        (file_url or "").lower()
    ]
    for suffix in ATTACHMENT_SUFFIXES:
        if any(candidate.endswith(suffix) for candidate in candidates if candidate):
            return suffix.lstrip(".")
    return ""


def extract_filename_from_url(href: str) -> str:
    """从下载链接里提取真实文件名"""
    parsed = urlparse(href or "")
    query_params = parse_qs(parsed.query)

    for key in ("filename", "file", "name", "download"):
        values = query_params.get(key)
        if values and values[0]:
            return unquote(values[0].split("/")[-1])

    if parsed.path:
        return unquote(parsed.path.rsplit("/", 1)[-1])

    return ""


def build_attachment_filename(link_text: str, href: str) -> str:
    """优先用链接文字，其次回退到链接最后一段"""
    cleaned_text = normalize_content_text(link_text or "").strip("：: ")
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()
    cleaned_text = re.sub(
        rf"({ATTACHMENT_SUFFIX_PATTERN})(?:\s+[xX])?$",
        r"\1",
        cleaned_text,
        flags=re.IGNORECASE
    )
    filename = extract_filename_from_url(href)
    suffix = Path(filename).suffix if filename else ""

    if cleaned_text:
        lowered_text = cleaned_text.lower()
        if lowered_text.endswith(ATTACHMENT_SUFFIXES):
            if suffix and not lowered_text.endswith(suffix.lower()):
                for candidate_suffix in ATTACHMENT_SUFFIXES:
                    if lowered_text.endswith(candidate_suffix):
                        return f"{cleaned_text[:-len(candidate_suffix)]}{suffix}"
            return cleaned_text
        if suffix and lowered_text not in GENERIC_ATTACHMENT_TEXTS:
            return f"{cleaned_text}{suffix}"
        if lowered_text not in GENERIC_ATTACHMENT_TEXTS:
            return cleaned_text

    if filename:
        return filename

    return cleaned_text or "未命名附件"


class JiangsuHRSSScraper(BaseScraper):
    """江苏省人力资源和社会保障厅爬虫"""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        ajax_url: str | None = None,
        ajax_params: Dict[str, str] | None = None,
    ):
        super().__init__()
        if base_url is None:
            resolved_base_url = DEFAULT_BASE_URL
        else:
            resolved_base_url = base_url.strip()
            if not resolved_base_url:
                raise ValueError("source base_url 不能为空")

        self.base_url = resolved_base_url
        self.site_root = build_site_root(self.base_url)
        self.ajax_url = ajax_url or urljoin(self.site_root, DEFAULT_AJAX_PATH)
        self.ajax_params = build_ajax_params(self.base_url, ajax_params)
        self._reset_scrape_metrics()

    def _reset_scrape_metrics(self) -> None:
        """重置单次抓取统计。"""
        self.reset_transport_metrics()
        self.scrape_metrics = {
            "pages_fetched": 0,
            "page_failures": 0,
            "detail_pages_fetched": 0,
            "detail_failures": 0,
            "raw_items_collected": 0,
            "skipped_items": 0,
            "request_retries": 0,
        }

    def _increment_metric(self, key: str, value: int = 1) -> None:
        self.scrape_metrics[key] = int(self.scrape_metrics.get(key, 0) or 0) + value

    def _snapshot_scrape_metrics(self) -> Dict[str, int]:
        return {
            **self.scrape_metrics,
            "request_retries": int(getattr(self, "request_retry_count", 0) or 0),
        }

    @staticmethod
    def _looks_like_list_payload(html: str) -> bool:
        lowered_html = (html or "").lower()
        return any(marker in lowered_html for marker in ("<datastore", "<record", "<![cdata["))

    @staticmethod
    def _looks_like_error_detail_page(soup: BeautifulSoup, content: str, attachments: List[Dict[str, Any]]) -> bool:
        if attachments:
            return False

        title_text = normalize_content_text(soup.title.get_text(" ", strip=True) if soup.title else "")
        body = soup.find("body")
        body_text = normalize_content_text(body.get_text(" ", strip=True) if body else "")
        merged_text = f"{title_text}\n{content}\n{body_text}".strip().lower()
        if not merged_text:
            return True

        if any(marker in merged_text for marker in DETAIL_ERROR_MARKERS):
            return True

        return len(merged_text) <= 80 and bool(re.search(r"\b(?:403|404|500|502|503)\b", merged_text))

    def resolve_detail_url(self, href: str) -> str:
        """把列表页相对链接转成当前 source 对应的绝对链接。"""
        return urljoin(self.base_url, href or "")

    async def scrape_detail_page(self, url: str) -> Dict[str, Any]:
        """
        抓取详情页内容

        Args:
            url: 详情页 URL

        Returns:
            Dict[str, Any]: 提取的正文和附件
        """
        try:
            response = await self.fetch(url)
            html = response.text
            soup = BeautifulSoup(html, "html.parser")

            content = ""
            attachments = []
            content_container = self.find_content_container(soup)

            if content_container:
                attachments = self.extract_attachments(content_container, url)
                content = self.extract_content_text(content_container, attachments)

            if not content:
                for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer']):
                    tag.decompose()
                body = soup.find("body")
                if body:
                    attachments = attachments or self.extract_attachments(body, url)
                    content = normalize_content_text(body.get_text("\n", strip=True))

            content = normalize_content_text(content)
            if self._looks_like_error_detail_page(soup, content, attachments):
                logger.warning(f"详情页响应疑似错误页，按失败处理: {url}")
                return {"content": "", "attachments": [], "detail_failed": True}

            logger.debug(
                f"详情页抓取成功: {url}, 内容长度: {len(content)}, 附件数量: {len(attachments)}"
            )
            return {
                "content": content,
                "attachments": attachments,
                "detail_failed": False,
            }

        except Exception as e:
            logger.error(f"抓取详情页失败: {url} - {e}")
            return {"content": "", "attachments": [], "detail_failed": True}

    def find_content_container(self, soup: BeautifulSoup):
        """定位正文容器"""
        selectors = [
            "#Zoom",
            ".TRS_Editor",
            ".content_box_nr #Zoom",
            ".content_box_nr",
            ".article-content",
            ".main-content",
            ".detail-content",
            ".content",
            ".text",
        ]

        for selector in selectors:
            container = soup.select_one(selector)
            if container:
                return container

        return None

    def extract_attachments(self, content_container, page_url: str) -> List[Dict[str, Any]]:
        """提取正文中的结构化附件"""
        attachments = []
        seen_urls = set()

        for link in content_container.find_all("a", href=True):
            href = (link.get("href") or "").strip()
            text = normalize_content_text(link.get_text(" ", strip=True))

            if not href:
                continue

            file_url = urljoin(page_url, href)
            filename = build_attachment_filename(text, file_url)
            file_type = infer_attachment_type(filename, file_url)
            if not file_type or file_url in seen_urls:
                continue
            attachments.append({
                "filename": filename,
                "file_url": file_url,
                "file_type": file_type,
            })
            seen_urls.add(file_url)

        return attachments

    def extract_content_text(self, content_container, attachments: List[Dict[str, Any]] | None = None) -> str:
        """从正文容器中提取正文"""
        for selector in [".ckywj", ".dyby", ".clear", "script", "style"]:
            for node in content_container.select(selector):
                node.decompose()

        attachment_names = {
            normalize_content_text(attachment.get("filename", ""))
            for attachment in (attachments or [])
            if attachment.get("filename")
        }

        blocks = []
        for table in content_container.find_all("table", recursive=True):
            table_rows = []
            for row in table.find_all("tr", recursive=True):
                cells = [
                    normalize_content_text(cell.get_text(" ", strip=True))
                    for cell in row.find_all(["th", "td"], recursive=False)
                ]
                cells = [cell for cell in cells if cell and not is_noise_text(cell)]
                if cells:
                    table_rows.append(" | ".join(cells))
            if table_rows:
                blocks.append("\n".join(table_rows))
            table.decompose()

        for block in content_container.find_all(["p", "li"], recursive=True):
            text = block.get_text(" ", strip=True)
            text = normalize_content_text(text)
            if attachment_names and any(name and name in text for name in attachment_names):
                continue
            if text and not is_noise_text(text):
                blocks.append(text)

        if not blocks:
            fallback_text = normalize_content_text(content_container.get_text("\n", strip=True))
            if fallback_text:
                blocks.append(fallback_text)

        return "\n\n".join(blocks)

    async def scrape_first_page(self) -> List[Dict[str, Any]]:
        """
        抓取首页数据

        Returns:
            List[Dict[str, Any]]: 首页数据列表
        """
        logger.info("开始抓取首页数据")
        response = await self.fetch(self.base_url)
        html = response.text

        # 使用正则表达式提取 datastore 内容
        datastore_pattern = r'<datastore>(.*?)</datastore>'
        datastore_match = re.search(datastore_pattern, html, re.DOTALL)

        if not datastore_match:
            logger.warning("未找到 <datastore> 标签")
            raise RuntimeError("首页响应结构不符合预期：未找到 <datastore> 标签")

        datastore_content = datastore_match.group(1)

        # 提取所有 record 标签
        record_pattern = r'<record><!\[CDATA\[(.*?)\]\]></record>'
        record_matches = re.findall(record_pattern, datastore_content, re.DOTALL)
        if not record_matches and not self._looks_like_list_payload(datastore_content):
            raise RuntimeError("首页响应结构不符合预期")

        results = []
        for cdata_text in record_matches:
            try:
                # 解析 CDATA 中的 HTML
                record_soup = BeautifulSoup(cdata_text, "html.parser")
                link_tag = record_soup.find("a")
                if not link_tag:
                    self._increment_metric("skipped_items")
                    continue
                href = (link_tag.get("href") or "").strip()
                if not href:
                    self._increment_metric("skipped_items")
                    continue

                # 提取标题
                title_span = link_tag.find("span", class_="list_title")
                if not title_span:
                    self._increment_metric("skipped_items")
                    continue
                title = title_span.get_text(strip=True)

                # 提取 URL
                url = self.resolve_detail_url(href)

                # 提取发布日期
                date_tag = link_tag.find("i")
                date_str = date_tag.get_text(strip=True) if date_tag else ""
                publish_date = self.parse_date(date_str)

                # 抓取详情页内容
                detail_payload = await self.scrape_detail_page(url)
                self._increment_metric("detail_pages_fetched")
                if detail_payload.get("detail_failed"):
                    self._increment_metric("detail_failures")
                await self.delay()

                results.append({
                    "title": title,
                    "url": url,
                    "publish_date": publish_date,
                    "content": detail_payload.get("content", ""),
                    "attachments": detail_payload.get("attachments", []),
                    "detail_failed": bool(detail_payload.get("detail_failed")),
                })
            except Exception as e:
                logger.error(f"解析记录失败: {e}")
                self._increment_metric("skipped_items")
                continue

        logger.info(f"首页抓取完成，共 {len(results)} 条记录")
        return results

    async def scrape_page(self, page_num: int) -> List[Dict[str, Any]]:
        """
        抓取指定页数据（Ajax 翻页）

        Args:
            page_num: 页码（从 2 开始）

        Returns:
            List[Dict[str, Any]]: 数据列表
        """
        logger.info(f"开始抓取第 {page_num} 页数据")

        # Ajax 请求参数（GET 方法）
        params = dict(self.ajax_params)
        params["page"] = str(page_num)

        response = await self.fetch(
            self.ajax_url,
            method="GET",
            params=params
        )

        html = response.text

        # 使用正则表达式提取 record 标签（和首页一样的格式）
        record_pattern = r'<record><!\[CDATA\[(.*?)\]\]></record>'
        record_matches = re.findall(record_pattern, html, re.DOTALL)
        if not record_matches and not self._looks_like_list_payload(html):
            raise RuntimeError(f"第 {page_num} 页响应结构不符合预期")

        results = []
        for cdata_text in record_matches:
            try:
                # 解析 CDATA 中的 HTML
                record_soup = BeautifulSoup(cdata_text, "html.parser")
                link_tag = record_soup.find("a")
                if not link_tag:
                    self._increment_metric("skipped_items")
                    continue
                href = (link_tag.get("href") or "").strip()
                if not href:
                    self._increment_metric("skipped_items")
                    continue

                # 提取标题
                title_span = link_tag.find("span", class_="list_title")
                if not title_span:
                    self._increment_metric("skipped_items")
                    continue
                title = title_span.get_text(strip=True)

                # 提取 URL
                url = self.resolve_detail_url(href)

                # 提取发布日期
                date_tag = link_tag.find("i")
                date_str = date_tag.get_text(strip=True) if date_tag else ""
                publish_date = self.parse_date(date_str)

                # 抓取详情页内容
                detail_payload = await self.scrape_detail_page(url)
                self._increment_metric("detail_pages_fetched")
                if detail_payload.get("detail_failed"):
                    self._increment_metric("detail_failures")
                await self.delay()

                results.append({
                    "title": title,
                    "url": url,
                    "publish_date": publish_date,
                    "content": detail_payload.get("content", ""),
                    "attachments": detail_payload.get("attachments", []),
                    "detail_failed": bool(detail_payload.get("detail_failed")),
                })
            except Exception as e:
                logger.error(f"解析记录失败: {e}")
                self._increment_metric("skipped_items")
                continue

        logger.info(f"第 {page_num} 页抓取完成，共 {len(results)} 条记录")
        return results

    def _emit_collecting_progress(self, progress_callback: ProgressCallback | None) -> None:
        emit_progress(
            progress_callback,
            stage="collecting",
            stage_key="collect-pages",
            stage_label="正在采集源站页面",
            progress_mode="stage_only",
            metrics=self._snapshot_scrape_metrics(),
        )

    async def scrape(
        self,
        max_pages: int = 10,
        progress_callback: ProgressCallback | None = None,
    ) -> List[Dict[str, Any]]:
        """
        抓取多页数据

        Args:
            max_pages: 最大抓取页数

        Returns:
            List[Dict[str, Any]]: 所有数据列表
        """
        self._reset_scrape_metrics()
        all_results = []

        # 抓取首页
        try:
            first_page_results = await self.scrape_first_page()
        except Exception:
            self._increment_metric("page_failures")
            self._emit_collecting_progress(progress_callback)
            raise
        self._increment_metric("pages_fetched")
        all_results.extend(first_page_results)
        self.scrape_metrics["raw_items_collected"] = len(all_results)
        self._emit_collecting_progress(progress_callback)
        await self.delay()

        # 抓取后续页
        for page_num in range(2, max_pages + 1):
            try:
                page_results = await self.scrape_page(page_num)
                self._increment_metric("pages_fetched")
                if not page_results:
                    self.scrape_metrics["raw_items_collected"] = len(all_results)
                    self._emit_collecting_progress(progress_callback)
                    logger.info(f"第 {page_num} 页无数据，停止抓取")
                    break
                all_results.extend(page_results)
                self.scrape_metrics["raw_items_collected"] = len(all_results)
                self._emit_collecting_progress(progress_callback)
                await self.delay()
            except Exception as e:
                logger.error(f"抓取第 {page_num} 页失败: {e}")
                self._increment_metric("page_failures")
                self._emit_collecting_progress(progress_callback)
                break

        logger.success(f"抓取完成，共 {len(all_results)} 条记录")
        return all_results

    def parse_date(self, date_str: str) -> datetime:
        """
        解析日期字符串

        Args:
            date_str: 日期字符串

        Returns:
            datetime: 日期对象
        """
        if not date_str:
            return datetime.now(timezone.utc)

        # 支持的日期格式
        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y年%m月%d日",
            "%Y.%m.%d"
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        logger.warning(f"无法解析日期: {date_str}，使用当前时间")
        return datetime.now(timezone.utc)
