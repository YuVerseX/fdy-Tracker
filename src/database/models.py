"""数据库模型定义"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Source(Base):
    """数据源配置表"""
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="数据源名称")
    province = Column(String(50), nullable=False, comment="省份")
    source_type = Column(String(50), nullable=False, comment="数据源类型")
    base_url = Column(String(500), nullable=False, comment="基础URL")
    scraper_class = Column(String(100), nullable=False, comment="爬虫类名")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    # 关系
    posts = relationship("Post", back_populates="source")


class SchedulerConfig(Base):
    """定时抓取配置表"""
    __tablename__ = "scheduler_configs"

    id = Column(Integer, primary_key=True, index=True)
    enabled = Column(Boolean, default=True, nullable=False, comment="是否启用定时抓取")
    interval_seconds = Column(Integer, default=7200, nullable=False, comment="抓取间隔（秒）")
    default_source_id = Column(Integer, ForeignKey("sources.id"), nullable=False, comment="默认抓取数据源")
    default_max_pages = Column(Integer, default=5, nullable=False, comment="默认抓取页数")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    source = relationship("Source")


class Post(Base):
    """招聘信息表"""
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False, comment="数据源ID")
    title = Column(String(500), nullable=False, index=True, comment="标题")
    content = Column(Text, comment="正文内容")
    publish_date = Column(DateTime, index=True, comment="发布日期")
    canonical_url = Column(String(1000), unique=True, nullable=False, comment="规范化URL")
    original_url = Column(String(1000), comment="原始URL")
    duplicate_status = Column(String(20), default="none", nullable=False, index=True, comment="去重状态：none/primary/duplicate")
    duplicate_group_key = Column(String(120), index=True, comment="重复组 key")
    primary_post_id = Column(Integer, ForeignKey("posts.id"), comment="主记录 ID")
    duplicate_reason = Column(String(80), index=True, comment="重复原因")
    duplicate_checked_at = Column(DateTime, comment="最近一次去重检查时间")

    # 过滤相关
    is_counselor = Column(Boolean, default=False, index=True, comment="是否为辅导员岗位")
    confidence_score = Column(Float, comment="匹配置信度")
    counselor_scope = Column(String(20), default="none", index=True, comment="辅导员范围：none/dedicated/contains")
    has_counselor_job = Column(Boolean, default=False, index=True, comment="是否含辅导员岗位")

    # 元数据
    scraped_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="抓取时间")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    # 关系
    source = relationship("Source", back_populates="posts")
    primary_post = relationship("Post", remote_side=[id], backref="duplicate_posts", foreign_keys=[primary_post_id])
    fields = relationship("PostField", back_populates="post", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="post", cascade="all, delete-orphan")
    analysis = relationship("PostAnalysis", back_populates="post", uselist=False, cascade="all, delete-orphan")
    insight = relationship("PostInsight", back_populates="post", uselist=False, cascade="all, delete-orphan")
    jobs = relationship("PostJob", back_populates="post", cascade="all, delete-orphan")


class PostField(Base):
    """招聘信息结构化字段表"""
    __tablename__ = "post_fields"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, comment="招聘信息ID")
    field_name = Column(String(100), nullable=False, comment="字段名称")
    field_value = Column(Text, comment="字段值")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    # 关系
    post = relationship("Post", back_populates="fields")


class Attachment(Base):
    """附件表"""
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, comment="招聘信息ID")
    filename = Column(String(500), nullable=False, comment="文件名")
    file_url = Column(String(1000), nullable=False, comment="文件URL")
    file_type = Column(String(50), comment="文件类型")
    file_size = Column(Integer, comment="文件大小（字节）")
    is_downloaded = Column(Boolean, default=False, comment="是否已下载")
    local_path = Column(String(1000), comment="本地路径")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    # 关系
    post = relationship("Post", back_populates="attachments")


class PostAnalysis(Base):
    """帖子分析结果表"""
    __tablename__ = "post_analyses"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, unique=True, comment="招聘信息ID")
    analysis_status = Column(String(50), default="pending", nullable=False, index=True, comment="分析状态")
    analysis_provider = Column(String(50), comment="分析提供方")
    model_name = Column(String(100), comment="分析模型")
    prompt_version = Column(String(50), comment="提示词版本")
    event_type = Column(String(50), index=True, comment="事件类型")
    recruitment_stage = Column(String(50), comment="招聘阶段")
    tracking_priority = Column(String(20), index=True, comment="关注优先级")
    school_name = Column(String(255), comment="学校或单位")
    city = Column(String(100), index=True, comment="城市")
    should_track = Column(Boolean, default=True, comment="是否值得持续关注")
    summary = Column(Text, comment="AI 摘要")
    tags_json = Column(Text, comment="标签 JSON")
    entities_json = Column(Text, comment="实体 JSON")
    raw_result_json = Column(Text, comment="原始分析结果 JSON")
    error_message = Column(Text, comment="分析失败原因")
    analyzed_at = Column(DateTime, comment="分析完成时间")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    post = relationship("Post", back_populates="analysis")


class PostJob(Base):
    """帖子岗位级结果表"""
    __tablename__ = "post_jobs"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, index=True, comment="招聘信息ID")
    job_name = Column(String(255), nullable=False, comment="岗位名称")
    recruitment_count = Column(String(100), comment="招聘人数")
    education_requirement = Column(String(255), comment="学历要求")
    major_requirement = Column(Text, comment="专业要求")
    location = Column(String(255), comment="工作地点")
    political_status = Column(String(100), comment="政治面貌")
    source_type = Column(String(50), nullable=False, default="derived", index=True, comment="来源类型：attachment/field/ai")
    is_counselor = Column(Boolean, default=False, index=True, comment="是否辅导员岗位")
    confidence_score = Column(Float, comment="岗位识别置信度")
    raw_payload_json = Column(Text, comment="原始岗位 JSON")
    sort_order = Column(Integer, default=0, comment="展示顺序")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    post = relationship("Post", back_populates="jobs")


class PostInsight(Base):
    """帖子 AI 统计字段表"""
    __tablename__ = "post_insights"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, unique=True, comment="招聘信息ID")
    insight_status = Column(String(50), default="pending", nullable=False, index=True, comment="统计抽取状态")
    insight_provider = Column(String(50), comment="统计提供方")
    model_name = Column(String(100), comment="统计模型")
    prompt_version = Column(String(50), comment="提示词版本")
    recruitment_count_total = Column(Integer, comment="总招聘人数")
    counselor_recruitment_count = Column(Integer, comment="辅导员招聘人数")
    degree_floor = Column(String(50), index=True, comment="学历下限")
    city_list_json = Column(Text, comment="城市列表 JSON")
    gender_restriction = Column(String(50), index=True, comment="性别限制")
    political_status_required = Column(String(100), comment="政治面貌要求")
    deadline_text = Column(String(255), comment="截止时间原文")
    deadline_date = Column(String(20), index=True, comment="截止日期")
    deadline_status = Column(String(50), index=True, comment="截止状态")
    has_written_exam = Column(Boolean, comment="是否包含笔试")
    has_interview = Column(Boolean, comment="是否包含面试")
    has_attachment_job_table = Column(Boolean, comment="是否有附件岗位表")
    evidence_summary = Column(Text, comment="统计依据摘要")
    raw_result_json = Column(Text, comment="原始统计结果 JSON")
    error_message = Column(Text, comment="统计失败原因")
    analyzed_at = Column(DateTime, comment="统计完成时间")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="更新时间")

    post = relationship("Post", back_populates="insight")
