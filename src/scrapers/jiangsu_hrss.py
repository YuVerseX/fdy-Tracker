"""江苏省人社厅爬虫"""
from pathlib import Path
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from loguru import logger
from src.scrapers.base import BaseScraper
from src.services.task_progress import ProgressCallback, emit_progress

NOISE_TEXTS = {
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
}

ATTACHMENT_SUFFIXES = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar")
ATTACHMENT_SUFFIX_PATTERN = "|".join(re.escape(suffix) for suffix in ATTACHMENT_SUFFIXES)
GENERIC_ATTACHMENT_TEXTS = {"附件", "下载", "点击下载", "查看附件", "点击查看原文件"}


def is_noise_text(text: str) -> bool:
    """判断是否为正文噪音"""
    normalized = text.strip()
    if not normalized:
        return True
    if normalized in NOISE_TEXTS:
        return True
    if normalized.startswith("当前位置："):
        return True
    if normalized.startswith("发布日期："):
        return True
    if normalized.startswith("来源："):
        return True
    if normalized.startswith("字体：["):
        return True
    if normalized == "关闭本页打印本页":
        return True
    return False


def normalize_content_text(content: str) -> str:
    """清理正文文本，兼容历史脏数据"""
    if not content:
        return ""

    normalized = content.replace("\r", "\n").replace("\xa0", " ").replace("\u3000", " ")
    raw_lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    filtered_lines = [line for line in raw_lines if not is_noise_text(line)]

    if not filtered_lines:
        return ""

    fragmented_line_count = sum(len(line) <= 6 for line in filtered_lines)
    looks_fragmented = len(filtered_lines) >= 8 and fragmented_line_count / len(filtered_lines) > 0.35

    if looks_fragmented:
        normalized = "".join(filtered_lines)
        normalized = normalized.replace("点击查看原文件：", "")
        normalized = normalized.replace("关闭本页打印本页", "")
    else:
        normalized = "\n\n".join(filtered_lines)

    normalized = re.sub(r"(?<!\n\n)(附件[:：])", r"\n\n\1", normalized)
    normalized = re.sub(
        r"(?<!\n)(举报电话[:：]|咨询电话[:：]|监督电话[:：]|举报信箱[:：]|联系电话[:：])",
        r"\n\1",
        normalized
    )
    normalized = re.sub(r"(?<!\n\n)([一二三四五六七八九十]+、)", r"\n\n\1", normalized)
    normalized = re.sub(r"(?<!\n)(（[一二三四五六七八九十]+）)", r"\n\1", normalized)
    normalized = re.sub(r"(?<!\d)(?<!\n)([1-9][0-9]?[.、])(?=[^\d])", r"\n\1", normalized)
    normalized = re.sub(r"([0-9-]{7,})([1-9])(?=\.[\u4e00-\u9fff])", r"\1\n\2", normalized)
    normalized = re.sub(
        rf"({ATTACHMENT_SUFFIX_PATTERN})(?=(?:附件[:：]|[\u4e00-\u9fffA-Za-z]))",
        r"\1\n",
        normalized,
        flags=re.IGNORECASE
    )
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


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

    def __init__(self):
        super().__init__()
        self.base_url = "http://jshrss.jiangsu.gov.cn/col/col80382/index.html"
        self.ajax_url = "http://jshrss.jiangsu.gov.cn/module/web/jpage/dataproxy.jsp"

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

            logger.debug(
                f"详情页抓取成功: {url}, 内容长度: {len(content)}, 附件数量: {len(attachments)}"
            )
            return {
                "content": content,
                "attachments": attachments
            }

        except Exception as e:
            logger.error(f"抓取详情页失败: {url} - {e}")
            return {"content": "", "attachments": []}

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
            is_attachment = href.lower().endswith(ATTACHMENT_SUFFIXES) or text.lower().endswith(ATTACHMENT_SUFFIXES)
            if not is_attachment or file_url in seen_urls:
                continue

            filename = build_attachment_filename(text, file_url)
            attachments.append({
                "filename": filename,
                "file_url": file_url,
                "file_type": infer_attachment_type(filename, file_url)
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
            return []

        datastore_content = datastore_match.group(1)

        # 提取所有 record 标签
        record_pattern = r'<record><!\[CDATA\[(.*?)\]\]></record>'
        record_matches = re.findall(record_pattern, datastore_content, re.DOTALL)

        results = []
        for cdata_text in record_matches:
            try:
                # 解析 CDATA 中的 HTML
                record_soup = BeautifulSoup(cdata_text, "html.parser")
                link_tag = record_soup.find("a")
                if not link_tag:
                    continue

                # 提取标题
                title_span = link_tag.find("span", class_="list_title")
                if not title_span:
                    continue
                title = title_span.get_text(strip=True)

                # 提取 URL
                url = link_tag.get("href", "")
                if url.startswith("/"):
                    url = f"http://jshrss.jiangsu.gov.cn{url}"

                # 提取发布日期
                date_tag = link_tag.find("i")
                date_str = date_tag.get_text(strip=True) if date_tag else ""
                publish_date = self.parse_date(date_str)

                # 抓取详情页内容
                detail_payload = await self.scrape_detail_page(url)
                await self.delay()

                results.append({
                    "title": title,
                    "url": url,
                    "publish_date": publish_date,
                    "content": detail_payload.get("content", ""),
                    "attachments": detail_payload.get("attachments", [])
                })
            except Exception as e:
                logger.error(f"解析记录失败: {e}")
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
        params = {
            "columnid": "80382",
            "unitid": "325517",
            "webid": "67",
            "page": str(page_num)
        }

        response = await self.fetch(
            self.ajax_url,
            method="GET",
            params=params
        )

        html = response.text

        # 使用正则表达式提取 record 标签（和首页一样的格式）
        record_pattern = r'<record><!\[CDATA\[(.*?)\]\]></record>'
        record_matches = re.findall(record_pattern, html, re.DOTALL)

        results = []
        for cdata_text in record_matches:
            try:
                # 解析 CDATA 中的 HTML
                record_soup = BeautifulSoup(cdata_text, "html.parser")
                link_tag = record_soup.find("a")
                if not link_tag:
                    continue

                # 提取标题
                title_span = link_tag.find("span", class_="list_title")
                if not title_span:
                    continue
                title = title_span.get_text(strip=True)

                # 提取 URL
                url = link_tag.get("href", "")
                if url.startswith("/"):
                    url = f"http://jshrss.jiangsu.gov.cn{url}"

                # 提取发布日期
                date_tag = link_tag.find("i")
                date_str = date_tag.get_text(strip=True) if date_tag else ""
                publish_date = self.parse_date(date_str)

                # 抓取详情页内容
                detail_payload = await self.scrape_detail_page(url)
                await self.delay()

                results.append({
                    "title": title,
                    "url": url,
                    "publish_date": publish_date,
                    "content": detail_payload.get("content", ""),
                    "attachments": detail_payload.get("attachments", [])
                })
            except Exception as e:
                logger.error(f"解析记录失败: {e}")
                continue

        logger.info(f"第 {page_num} 页抓取完成，共 {len(results)} 条记录")
        return results

    def _emit_collecting_progress(
        self,
        progress_callback: ProgressCallback | None,
        *,
        pages_fetched: int,
        detail_pages_fetched: int,
        raw_items_collected: int,
    ) -> None:
        emit_progress(
            progress_callback,
            stage="collecting",
            stage_key="collect-pages",
            stage_label="正在采集源站页面",
            progress_mode="stage_only",
            metrics={
                "pages_fetched": pages_fetched,
                "detail_pages_fetched": detail_pages_fetched,
                "raw_items_collected": raw_items_collected,
            },
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
        all_results = []
        pages_fetched = 0
        detail_pages_fetched = 0

        # 抓取首页
        first_page_results = await self.scrape_first_page()
        pages_fetched += 1
        detail_pages_fetched += len(first_page_results)
        all_results.extend(first_page_results)
        self._emit_collecting_progress(
            progress_callback,
            pages_fetched=pages_fetched,
            detail_pages_fetched=detail_pages_fetched,
            raw_items_collected=len(all_results),
        )
        await self.delay()

        # 抓取后续页
        for page_num in range(2, max_pages + 1):
            try:
                page_results = await self.scrape_page(page_num)
                if not page_results:
                    logger.info(f"第 {page_num} 页无数据，停止抓取")
                    break
                pages_fetched += 1
                detail_pages_fetched += len(page_results)
                all_results.extend(page_results)
                self._emit_collecting_progress(
                    progress_callback,
                    pages_fetched=pages_fetched,
                    detail_pages_fetched=detail_pages_fetched,
                    raw_items_collected=len(all_results),
                )
                await self.delay()
            except Exception as e:
                logger.error(f"抓取第 {page_num} 页失败: {e}")
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
