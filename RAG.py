import os
import requests
import json
# 导入FAISS库（Facebook AI Similarity Search）
# FAISS是一个高效的向量相似度搜索库，常用于：
# - 大规模向量检索
# - 最近邻搜索
# - 文本/图像嵌入向量的相似度匹配
import faiss
# 从dotenv库导入load_dotenv函数
# 用于从.env文件中加载环境变量（如API密钥、数据库配置等敏感信息）
# 这样可以避免将敏感信息硬编码在代码中
from dotenv import load_dotenv

load_dotenv(".env")

# 从functools模块导入lru_cache装饰器
# lru_cache是一个缓存装饰器，用于：
# - 缓存函数的返回结果，避免重复计算
# - 当相同参数再次调用时，直接返回缓存的结果
# - 自动管理缓存大小，淘汰最久未使用的缓存项
# ⚠️ 注意：lru_cache不适用于带有可变参数（如列表、字典）的函数
# 因为可变对象不可哈希，会导致异常行为
from functools import lru_cache

class BaseLLM:
    @lru_cache(maxsize=1024)
    def chat(self, text):
        return self._chat(text)
    def _chat(self, text):
        raise NotImplementedError
    
from openai import OpenAI

class OpenAILLM(BaseLLM):
    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv('DEEPSEEK_API_KEY'),
            base_url=os.getenv("OPENAI_API_BASE")
        )
        
    def chat(self, text, messages=[]):
        if not messages:
            messages = [{"role": "user", "content": text}]
        response = self.client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=messages,
            stream=True,
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}}
        )
        for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                print(content, end="", flush=True)
    
openai_bot = OpenAILLM()
# openai_bot.chat("你好")

knowledge_list = [
    "剑桥大学的校长是马冬梅，马教授是一名计算机专业的教授，她的主要研究方向是自然语言处理",
    "牛津大学的软件学院院长是李磊，李教授是一名计算机专业的教授，他的主要研究方向是机器学习",
    "hit 有五万名学生",
    "wit 有三万名学生",
    "huts 的医学院是中部地区最好的医学院，最擅长临床医学的研究",
]

# 创建一个1024维的FAISS向量数据库，使用L2距离进行相似性搜索
hit_vd = faiss.IndexFlatL2(1024)

# 导入NumPy库并简写为np
# NumPy（Numerical Python）是Python科学计算的核心库，用于：
# - 高效的多维数组（ndarray）操作
# - 数学运算（线性代数、傅里叶变换、随机数等）
# - 广播机制实现不同形状数组的运算
# - 作为其他科学计算库的基础（Pandas、SciPy、TensorFlow等）
# 在AI/机器学习中常用于：
# - 处理向量嵌入（embeddings）
# - 数据预处理和特征工程
# - 与FAISS等向量库配合进行相似度计算
import numpy as np
# 使用硅基流动 SiliconFlow 的 bge-m3 模型生成 embedding（免费）
# bge-m3 输出 1024 维向量，对应上方 FAISS 索引的维度
@lru_cache(maxsize=1024)
def get_embedding(texts, model="BAAI/bge-m3"):
    if isinstance(texts, str):
        texts = [texts]
    else:
        texts = list(texts)
    sf_api_key = os.getenv("SILICONFLOW_API_KEY")
    if not sf_api_key or sf_api_key.startswith("sk-在此"):
        raise ValueError(
            "请先在 .env 文件中填入真实的 SILICONFLOW_API_KEY（硅基流动平台获取）"
        )
    sf_client = OpenAI(
        api_key=sf_api_key,
        base_url=os.getenv("SILICONFLOW_BASE_URL"),
    )
    response = sf_client.embeddings.create(
        input=texts,
        model=model,
    )
    # 使用指定的 model 对 texts 中的文本进行嵌入向量的生成。
    embs = [e.embedding for e in response.data]
    return embs

# 生成 embedding
embs = get_embedding(tuple(knowledge_list))
# 将 embedding 添加到 faiss 索引中

hit_vd.add(np.array(embs).astype("float32"))

prompt = "请告诉我牛津大学软件学院院长的研究方向是什么？"
query_vector = get_embedding(prompt)[0]

# 接下来我们来观察一下在我们编造的数据上，使用 rag 检索增强方案能够带来怎样的效果提升
distances, indices = hit_vd.search(np.array([query_vector]).astype('float32'), 2)

research_result = [knowledge_list[i] for i in indices.tolist()[0]]
print(f"查询的问题是：{prompt}\n检索到的答案是：{research_result}")

print("===== 不使用 RAG 的回答 =====")
openai_bot.chat(prompt)
print("\n\n===== 使用 RAG 的回答 =====")
openai_bot.chat(f"从知识库中检索到了相关知识：：{research_result}\n{prompt}")