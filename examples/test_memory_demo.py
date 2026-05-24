"""手动测试记忆系统 —— 不需要 LLM API key，直接测试存储层。"""
import sys
sys.path.insert(0, ".")

from src.storage.content_store import ContentStore
from src.storage.memory_vector_store import MemoryVectorStore

print("=" * 60)
print("记忆系统手动测试")
print("=" * 60)

# 1. 初始化
store = ContentStore(database_url="sqlite:///./data/content_ops.db")
memory_store = MemoryVectorStore(persist_dir="data/chroma")

print("\n✓ 存储初始化成功")
print(f"  当前记忆数量: {store.count_memories()}")

# 2. 写入记忆
print("\n--- 写入记忆 ---")
memories_to_save = [
    ("mem_test_01", "用户喜欢简洁风格，不要太多修饰词", "preference", 0.9),
    ("mem_test_02", "用户的品牌名是 TechFlow，做 AI 效率工具", "fact", 0.8),
    ("mem_test_03", "用户偏好小红书平台，目标受众是 25-35 岁职场人", "preference", 0.85),
    ("mem_test_04", "上次写的咖啡测评反响很好，用户想继续这个系列", "context", 0.6),
    ("mem_test_05", "用户要求所有内容都要有明确的 CTA（行动号召）", "instruction", 0.95),
]

for mid, content, category, importance in memories_to_save:
    result = store.save_memory(mid, content, category, importance=importance)
    memory_store.add(mid, content, category)
    print(f"  ✓ 已保存: [{category}] {content[:30]}...")

print(f"\n  总记忆数: {store.count_memories()}")

# 3. 语义检索测试
print("\n--- 语义检索测试 ---")
test_queries = [
    "写作风格偏好",
    "品牌信息",
    "目标平台和受众",
    "之前写过什么内容",
    "写内容有什么要求",
]

for query in test_queries:
    results = memory_store.query(query, n_results=3, threshold=0.3)
    print(f"\n  查询: '{query}'")
    if results:
        for r in results:
            print(f"    → [{r['category']}] {r['content'][:40]}... (相似度: {r['similarity']})")
    else:
        print(f"    → 无匹配结果（阈值 0.3）")

# 4. SQL 文本搜索兜底
print("\n--- SQL 文本搜索 ---")
text_results = store.search_memories_text("用户")
print(f"  搜索 '用户': 找到 {len(text_results)} 条")
for r in text_results:
    print(f"    → [{r['category']}] {r['content'][:40]}...")

# 5. 模拟 auto-recall
print("\n--- 模拟 Auto-Recall ---")
print("  场景: 用户说 '帮我写一篇小红书文案'")
from src.api.services.chat_agent import ChatAgentService

service = ChatAgentService(store=store, memory_store=memory_store)
context = service._auto_recall("帮我写一篇小红书文案")
if context:
    print(f"  注入的记忆上下文:")
    print(f"  {context}")
else:
    print("  （无相关记忆被召回）")

# 6. 清理测试数据（可选）
print("\n--- 清理 ---")
cleanup = input("是否删除测试记忆？(y/N): ").strip().lower()
if cleanup == "y":
    for mid, _, _, _ in memories_to_save:
        store.delete_memory(mid)
        memory_store.delete(mid)
    print("  ✓ 已清理")
else:
    print("  保留测试记忆（下次启动 Chat 时会被 auto-recall）")

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)
