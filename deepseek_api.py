# Please install OpenAI SDK first: `pip3 install openai`
import os
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

print("DEEPSEEK_API_KEY:", os.environ.get("DEEPSEEK_API_KEY"))

client = OpenAI(
    api_key=os.environ.get('DEEPSEEK_API_KEY'),
    base_url="https://api.deepseek.com")

response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[
        {"role": "system", "content": "你是一个厨师，拥有20年烹饪经验，脾气火爆，喜欢用比喻和夸张的手法表达观点。"},
        {"role": "user", "content": "怎么做宫保鸡丁"},
    ],
    stream=True,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}}
)

for chunk in response:
        print(chunk.choices[0].delta.content, end="", flush=True)