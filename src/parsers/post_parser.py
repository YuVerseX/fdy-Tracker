"""招聘信息智能解析器"""
import re
from typing import Dict, Optional, List
from loguru import logger


class PostParser:
    """招聘信息结构化字段解析器"""
    MAJOR_STOPWORDS = [
        '具备报考岗位要求',
        '岗位要求',
        '有关规定',
        '经过考核',
        '名单公示',
        '公开招聘',
        '拟聘用人员',
        '招聘公告'
    ]

    # 性别识别关键词
    GENDER_KEYWORDS = {
        'male': ['男', '男性', '限男', '仅限男性', '要求男'],
        'female': ['女', '女性', '限女', '仅限女性', '要求女'],
        'unlimited': ['不限', '男女不限', '性别不限', '不限性别']
    }

    # 学历识别关键词
    EDUCATION_KEYWORDS = {
        'doctor': ['博士', '博士研究生', '博士学位'],
        'master': ['硕士', '硕士研究生', '研究生学历', '硕士学位'],
        'bachelor': ['本科', '学士', '大学本科', '本科学历', '学士学位'],
        'college': ['专科', '大专', '高职']
    }

    # 学历中文映射
    EDUCATION_DISPLAY = {
        'doctor': '博士',
        'master': '硕士',
        'bachelor': '本科',
        'college': '专科'
    }

    def __init__(self):
        pass

    def parse(self, title: str, content: str) -> Dict[str, Optional[str]]:
        """
        解析招聘信息,提取结构化字段

        Args:
            title: 标题
            content: 正文内容

        Returns:
            Dict[str, Optional[str]]: 结构化字段字典
        """
        text = f"{title}\n{content}"

        fields = {
            'gender': self.extract_gender(text),
            'education': self.extract_education(text),
            'major': self.extract_major(text),
            'location': self.extract_location(text),
            'count': self.extract_count(text),
            'registration_time': self.extract_registration_time(text),
            'age_requirement': self.extract_age(text),
            'political_status': self.extract_political_status(text)
        }

        return fields

    def extract_gender(self, text: str) -> Optional[str]:
        """提取性别要求"""
        normalized_text = text.replace('\r', '')

        if any(keyword in normalized_text for keyword in ['男女不限', '性别不限', '不限性别']):
            return '不限'

        patterns = [
            r'(?:专职)?辅导员[（(](男|女)[)）]',
            r'(?:性别要求|性别)[：:]\s*([^\n，。；;]{1,12})',
            r'(?:仅限|限)\s*(男性|女性|男|女)',
        ]

        for pattern in patterns:
            match = re.search(pattern, normalized_text)
            if match:
                gender = self.normalize_gender(match.group(1))
                if gender:
                    return gender

        # 没有命中字段模式时，只认带性别语义的关键词，避免被“专业不限”误伤
        compact_text = text.replace(' ', '').replace('\n', '')
        if '男女不限' in compact_text or '性别不限' in compact_text or '不限性别' in compact_text:
            return '不限'
        if '辅导员（男）' in compact_text or '辅导员(男)' in compact_text:
            return '男'
        if '辅导员（女）' in compact_text or '辅导员(女)' in compact_text:
            return '女'
        for display, keywords in [('男', self.GENDER_KEYWORDS['male']), ('女', self.GENDER_KEYWORDS['female'])]:
            for keyword in keywords:
                if keyword in compact_text:
                    return display

        return None

    def extract_education(self, text: str) -> Optional[str]:
        """提取学历要求"""
        text = text.replace(' ', '').replace('\n', '')

        # 按优先级匹配(博士 > 硕士 > 本科 > 专科)
        for edu_level in ['doctor', 'master', 'bachelor', 'college']:
            for keyword in self.EDUCATION_KEYWORDS[edu_level]:
                if keyword in text:
                    return self.EDUCATION_DISPLAY[edu_level]

        return None

    def extract_major(self, text: str) -> Optional[str]:
        """提取专业要求"""
        # 匹配专业相关的模式
        patterns = [
            r'专业[：:]\s*([^\n，。；;]{2,50})',
            r'专业要求[：:]\s*([^\n，。；;]{2,50})',
            r'([一-龥（）()、/]{2,40}专业)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                major = self.clean_extracted_value(match.group(1))
                if major.endswith('专业'):
                    major = major[:-2]

                if (
                    len(major) > 1
                    and '不限' not in major
                    and not any(stopword in major for stopword in self.MAJOR_STOPWORDS)
                ):
                    return major

        return None

    def extract_location(self, text: str) -> Optional[str]:
        """提取工作地点"""
        # 匹配地点相关的模式
        patterns = [
            r'工作地点[：:]\s*([^\n，。；;]{2,30})',
            r'地点[：:]\s*([^\n，。；;]{2,30})',
            r'([\u4e00-\u9fa5]{2,10}市|[\u4e00-\u9fa5]{2,10}区|[\u4e00-\u9fa5]{2,10}县)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                location = self.clean_extracted_value(match.group(1))
                if len(location) > 1:
                    return location

        return None

    def extract_count(self, text: str) -> Optional[str]:
        """提取招聘人数"""
        # 匹配人数相关的模式
        patterns = [
            r'招聘[人]?数[量]?[：:]\s*(\d+)\s*[人名]?',
            r'招聘\s*(\d+)\s*[人名]',
            r'(\d+)\s*[人名]',
            r'[共计]?\s*(\d+)\s*个?岗位',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                count = str(int(match.group(1)))
                return f"{count}人"

        return None

    def extract_registration_time(self, text: str) -> Optional[str]:
        """提取报名时间"""
        # 匹配报名时间相关的模式
        patterns = [
            r'报名时间[：:]\s*(\d{4}[年\-/]\d{1,2}[月\-/]\d{1,2}[日]?\s*[-至—]\s*\d{4}[年\-/]\d{1,2}[月\-/]\d{1,2}[日]?)',
            r'报名时间[：:]\s*(\d{1,2}[月]\d{1,2}[日]\s*[-至—]\s*\d{1,2}[月]\d{1,2}[日])',
            r'(\d{4}[年\-/]\d{1,2}[月\-/]\d{1,2}[日]?\s*[-至—]\s*\d{4}[年\-/]\d{1,2}[月\-/]\d{1,2}[日]?)\s*报名',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()

        return None

    def extract_age(self, text: str) -> Optional[str]:
        """提取年龄要求"""
        # 匹配年龄相关的模式
        patterns = [
            r'年龄[：:]\s*(\d{2})\s*[-至—]\s*(\d{2})\s*[周]?岁',
            r'(\d{2})\s*[-至—]\s*(\d{2})\s*[周]?岁',
            r'年龄[：:]\s*(\d{2})\s*[周]?岁(?:以下|及以下)',
            r'(\d{2})\s*[周]?岁(?:以下|及以下)',
            r'年龄[：:]\s*(\d{2})\s*[周]?岁(?:以上|及以上)',
            r'(\d{2})\s*[周]?岁(?:以上|及以上)',
            r'(?:年龄[：:]?\s*)?(?:不超过|不得超过|小于等于|不大于)\s*(\d{2})\s*[周]?岁',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                if len(match.groups()) == 2:
                    return f"{match.group(1)}-{match.group(2)}岁"
                matched_text = match.group(0)
                age = match.group(1)
                if '以上' in matched_text:
                    return f"{age}岁以上"
                if '以下' in matched_text or '不超过' in matched_text or '不得超过' in matched_text:
                    return f"{age}岁以下"
                return f"{age}岁"

        return None

    def extract_political_status(self, text: str) -> Optional[str]:
        """提取政治面貌要求"""
        # 匹配政治面貌相关的关键词
        keywords = ['中共党员', '党员', '共产党员', '预备党员']

        for keyword in keywords:
            if keyword in text:
                return keyword

        return None

    def normalize_gender(self, value: str) -> Optional[str]:
        """标准化性别字段"""
        cleaned_value = self.clean_extracted_value(value).replace(' ', '')

        if any(keyword in cleaned_value for keyword in ['男女不限', '性别不限', '不限性别']):
            return '不限'
        if cleaned_value == '不限':
            return '不限'
        if '女' in cleaned_value and '男' not in cleaned_value:
            return '女'
        if '男' in cleaned_value and '女' not in cleaned_value:
            return '男'

        return None

    def clean_extracted_value(self, value: str) -> str:
        """清理提取出来的字段值"""
        cleaned_value = re.sub(r'^[\-\s、,，.:：]+', '', value).strip()
        cleaned_value = re.sub(r'^位于', '', cleaned_value)
        return cleaned_value.strip()


def parse_post_fields(title: str, content: str) -> List[Dict[str, str]]:
    """
    解析招聘信息并返回字段列表

    Args:
        title: 标题
        content: 正文内容

    Returns:
        List[Dict[str, str]]: 字段列表,每个字段包含 field_name 和 field_value
    """
    parser = PostParser()
    fields_dict = parser.parse(title, content)

    # 字段名称映射
    field_names = {
        'gender': '性别要求',
        'education': '学历要求',
        'major': '专业要求',
        'location': '工作地点',
        'count': '招聘人数',
        'registration_time': '报名时间',
        'age_requirement': '年龄要求',
        'political_status': '政治面貌'
    }

    # 转换为列表格式,过滤掉空值
    fields_list = []
    for key, value in fields_dict.items():
        if value:
            fields_list.append({
                'field_name': field_names.get(key, key),
                'field_value': value
            })

    logger.debug(f"解析出 {len(fields_list)} 个结构化字段")
    return fields_list
