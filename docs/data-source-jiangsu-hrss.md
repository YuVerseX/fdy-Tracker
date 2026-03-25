> 说明：本文记录江苏省人社厅数据源的页面结构和抓取思路。
>
> 如果本文和当前代码实现、根目录 `README.md` / `STATUS.md` 有冲突，以代码和根目录文档为准。

# 江苏省人社厅数据源实现方案

> 数据源：https://jshrss.jiangsu.gov.cn/col/col80382/index.html

## 1. 页面特征分析

### 1.1 基本信息
- **类型**：省属事业单位招聘公告汇总
- **总记录数**：2323 条（截至 2026-03-17）
- **分页**：每页 20 条，共 117 页
- **更新频率**：建议每 2 小时抓取一次

### 1.2 加载方式（混合型）

#### 首屏数据
```html
<datastore>
  <record>
    <![CDATA[
      <li>
        <a href="/art/2026/3/17/art_78506_11743459.html" target="_blank">
          <span class="list_title">标题文字</span>
          <i>2026-03-17</i>
        </a>
      </li>
    ]]>
  </record>
</datastore>
```

#### 翻页数据（Ajax）
- **接口**：`/module/web/jpage/dataproxy.jsp`
- **方法**：GET
- **参数**：
  ```
  columnid=80382
  unitid=325517
  webid=67
  page=2  # 页码从 2 开始
  ```

## 2. 抓取策略

### 2.1 首页抓取（静态 HTML）

```python
import httpx
from bs4 import BeautifulSoup
import re

async def fetch_first_page():
    """抓取首页（第1页）"""
    url = "https://jshrss.jiangsu.gov.cn/col/col80382/index.html"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=30.0)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')

        # 提取 datastore 中的 CDATA 内容
        datastore = soup.find('datastore')
        records = []

        for record in datastore.find_all('record'):
            cdata_content = record.string
            # 解析 CDATA 中的 HTML
            record_soup = BeautifulSoup(cdata_content, 'lxml')

            link_tag = record_soup.find('a')
            if link_tag:
                title = link_tag.find('span', class_='list_title').text.strip()
                href = link_tag['href']
                date = link_tag.find('i').text.strip()

                # 转换为绝对 URL
                full_url = f"https://jshrss.jiangsu.gov.cn{href}"

                records.append({
                    'title': title,
                    'url': full_url,
                    'publish_date': date
                })

        return records
```

### 2.2 翻页抓取（Ajax）

```python
async def fetch_page(page_num: int):
    """抓取指定页码（page >= 2）"""
    url = "https://jshrss.jiangsu.gov.cn/module/web/jpage/dataproxy.jsp"

    params = {
        'columnid': '80382',
        'unitid': '325517',
        'webid': '67',
        'page': str(page_num)
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, timeout=30.0)
        response.raise_for_status()

        # 返回的是 HTML 片段，直接解析
        soup = BeautifulSoup(response.text, 'lxml')

        records = []
        for li in soup.find_all('li'):
            link_tag = li.find('a')
            if link_tag:
                title = link_tag.find('span', class_='list_title').text.strip()
                href = link_tag['href']
                date = link_tag.find('i').text.strip()

                full_url = f"https://jshrss.jiangsu.gov.cn{href}"

                records.append({
                    'title': title,
                    'url': full_url,
                    'publish_date': date
                })

        return records
```

### 2.3 完整抓取流程

```python
async def fetch_all_pages(max_pages: int = None):
    """抓取所有页面"""
    all_records = []

    # 1. 抓取首页
    first_page_records = await fetch_first_page()
    all_records.extend(first_page_records)

    # 2. 抓取后续页面
    total_pages = 117  # 2323 / 20 ≈ 117
    if max_pages:
        total_pages = min(total_pages, max_pages)

    for page_num in range(2, total_pages + 1):
        try:
            records = await fetch_page(page_num)
            all_records.extend(records)

            # 请求间隔（避免封禁）
            await asyncio.sleep(random.uniform(1, 3))

        except Exception as e:
            logger.error(f"Failed to fetch page {page_num}: {e}")
            continue

    return all_records
```

## 3. 详情页抓取

### 3.1 详情页 URL 格式
```
https://jshrss.jiangsu.gov.cn/art/2026/3/17/art_78506_11743459.html
```

### 3.2 详情页解析

```python
async def fetch_detail(url: str):
    """抓取详情页"""
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=30.0)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')

        # 提取标题
        title = soup.find('h1', class_='article_title').text.strip()

        # 提取正文
        content_div = soup.find('div', class_='article_content')
        content = content_div.get_text(strip=True)

        # 提取附件链接
        attachments = []
        for link in content_div.find_all('a', href=True):
            href = link['href']
            if href.endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx')):
                full_url = f"https://jshrss.jiangsu.gov.cn{href}" if href.startswith('/') else href
                attachments.append({
                    'name': link.text.strip(),
                    'url': full_url
                })

        return {
            'title': title,
            'content': content,
            'attachments': attachments
        }
```

## 4. 过滤逻辑

### 4.1 标题关键词匹配

```python
def is_counselor_position(title: str) -> bool:
    """判断是否为专职辅导员招聘"""
    keywords = ['专职辅导员', '辅导员', '学生工作']
    exclude_keywords = ['兼职', '临时', '实习']

    # 必须包含关键词
    has_keyword = any(kw in title for kw in keywords)

    # 不能包含排除词
    has_exclude = any(kw in title for kw in exclude_keywords)

    return has_keyword and not has_exclude
```

### 4.2 地区判断

```python
def extract_region(title: str, content: str) -> str:
    """提取地区信息"""
    # 江苏省内城市
    jiangsu_cities = [
        '南京', '苏州', '无锡', '常州', '镇江', '扬州',
        '泰州', '南通', '盐城', '淮安', '宿迁', '连云港', '徐州'
    ]

    for city in jiangsu_cities:
        if city in title or city in content:
            return f'江苏-{city}'

    return '江苏'
```

## 5. 初始化策略

### 5.1 首次运行

**选项 1：只抓取最近 1 个月**
```python
# 优点：快速启动，数据量小
# 缺点：可能错过部分有效公告
max_pages = 10  # 约 200 条记录
```

**选项 2：抓取全部历史数据**
```python
# 优点：数据完整，可以分析历史趋势
# 缺点：初始化时间长（约 10-15 分钟）
max_pages = None  # 全部 117 页
```

**推荐**：选项 1（最近 1 个月），后续增量更新

### 5.2 增量更新

```python
async def incremental_update():
    """增量更新（只抓取前 3 页）"""
    new_records = []

    # 抓取首页
    first_page = await fetch_first_page()
    new_records.extend(first_page)

    # 抓取第 2-3 页
    for page_num in [2, 3]:
        records = await fetch_page(page_num)
        new_records.extend(records)

    # 去重（与数据库中已有记录对比）
    # ...

    return new_records
```

## 6. 定时任务配置

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# 每 2 小时增量更新
@scheduler.scheduled_job('interval', hours=2)
async def update_jiangsu_hrss():
    logger.info("开始更新江苏省人社厅数据...")
    new_records = await incremental_update()
    logger.info(f"发现 {len(new_records)} 条新记录")

    # 保存到数据库
    # ...

scheduler.start()
```

## 7. 数据源配置（sources 表）

```sql
INSERT INTO sources (name, region, type, entry_url, fetch_mode, selectors, enabled) VALUES (
    '江苏省人力资源和社会保障厅',
    '江苏',
    'official',
    'https://jshrss.jiangsu.gov.cn/col/col80382/index.html',
    'static',
    '{
        "list_selector": ".content_box_list ul li",
        "title_selector": "span.list_title",
        "link_selector": "a",
        "date_selector": "i",
        "ajax_url": "/module/web/jpage/dataproxy.jsp",
        "ajax_params": {
            "columnid": "80382",
            "unitid": "325517",
            "webid": "67"
        }
    }',
    1
);
```

## 8. 注意事项

### 8.1 反爬虫应对
- 请求间隔：1-3 秒
- User-Agent：使用真实浏览器 UA
- 失败重试：最多 3 次，指数退避

### 8.2 数据质量
- 标题可能包含多个岗位，需要解析详情页
- 附件中的岗位表是关键信息来源
- 部分公告可能是"补充公告"或"资格复审"，需要过滤

### 8.3 性能优化
- 首次初始化：并发抓取（限制 5 个并发）
- 增量更新：只抓取前 3 页（约 60 条记录）
- 详情页抓取：按需抓取（用户点击时再抓）

## 9. 测试检查清单

- [ ] 首页抓取正常
- [ ] 翻页抓取正常
- [ ] 详情页解析正确
- [ ] 附件链接可下载
- [ ] 标题过滤准确
- [ ] 地区识别正确
- [ ] 去重逻辑有效
- [ ] 定时任务稳定运行

---

**文档版本**：v1.0
**最后更新**：2026-03-17
**数据源状态**：✅ 已验证可用
