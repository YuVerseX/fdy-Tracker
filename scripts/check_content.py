from src.database.database import SessionLocal
from src.database.models import Post, PostField

db = SessionLocal()

# 检查有内容的记录
posts_with_content = db.query(Post).filter(Post.content != '').all()
print(f"有内容的记录数: {len(posts_with_content)}")

if posts_with_content:
    post = posts_with_content[0]
    print(f"示例记录 ID: {post.id}")
    print(f"标题: {post.title}")
    print(f"内容长度: {len(post.content)}")
    print(f"内容前100字符: {post.content[:100]}")

    # 检查字段
    fields = db.query(PostField).filter(PostField.post_id == post.id).all()
    print(f"\n结构化字段数: {len(fields)}")
    for field in fields:
        print(f"  - {field.field_name}: {field.field_value}")

db.close()
