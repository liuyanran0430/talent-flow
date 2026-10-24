# 导入dotenv模块
# python-dotenv库用于从.env文件中加载环境变量
# .env文件通常存放敏感配置信息，如：
# - API密钥（OPENAI_API_KEY、DEEPSEEK_API_KEY等）
# - 数据库连接字符串
# - 服务端口、调试模式等配置
import dotenv
# 导入操作系统模块，用于访问环境变量、文件路径等系统功能
import os

# 加载.env文件中的环境变量
dotenv.load_dotenv(".env")

# 从LangChain的OpenAI集成模块导入ChatOpenAI类
# ChatOpenAI用于调用OpenAI的聊天模型（GPT-4、GPT-3.5等）
# 也兼容其他符合OpenAI API格式的服务（DeepSeek、Azure等）
from langchain_openai import ChatOpenAI
# 从LangChain核心模块导入ChatPromptTemplate类
# 用于创建结构化的聊天提示词模板
# 支持多角色对话格式和变量插值
from langchain_core.prompts import ChatPromptTemplate
# 从LangChain核心模块导入StrOutputParser类
# StrOutputParser用于将LLM输出解析为纯字符串
# 是最简单的输出解析器，直接提取文本内容
from langchain_core.output_parsers import StrOutputParser
# 使用qwen-max模型进行聊天
# qwen = ChatOpenAI(
#     model="qwen-max",
#     api_key=os.getenv("DASHSCOPE_API_KEY"),
#     base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
# )

# 从LangChain核心模块导入tool装饰器
# tool装饰器用于将普通Python函数转换为LangChain工具
# 使AI代理（Agent）能够调用这些函数来完成特定任务
# 主要用途：
# - 让大语言模型具备调用外部函数的能力
# - 构建AI Agent的工具集（如搜索、计算、数据库查询等）
# - 实现Function Calling / Tool Use功能
from langchain_core.tools import tool

# 使用 @tool 装饰器定义乘法工具函数
@tool
def multiply(first_int: int, second_int: int) -> int:
    """Multiply two integers together."""  # 将两个整数相乘
    return first_int * second_int
 
# 使用 @tool 装饰器定义加法工具函数
@tool
def add(first_int: int, second_int: int) -> int:
    """add two integers together."""  # 将两个整数相加
    return first_int + second_int
    
# 使用 @tool 装饰器定义天气查询工具函数
@tool
def get_current_weather(location: str, unit: str) -> str:
    """
    Fetches the current weather for a given location and unit.
    
    Args:
    location (str): The name of the location. 
    unit (str): The unit of temperature (e.g., Celsius, Fahrenheit). 
    
    Returns:
    str: A string describing the current weather and temperature. 
    """
    return f"It's 20 {unit} in {location}"

# 将所有定义的工具函数收集到一个列表中，供 LangChain 使用
tools = [multiply, add, get_current_weather]

print("Name: ",get_current_weather.name)
print("\nDescription: ",get_current_weather.description)
print("\nArgs: ",get_current_weather.args)

# 从LangChain工具渲染模块导入render_text_description函数
# render_text_description用于将工具列表转换为文本描述
# 生成的文本可以嵌入到提示词中，让LLM了解可用的工具
# 主要用途：
# - 将Tool对象列表转换为人类可读的文本描述
# - 为AI Agent生成工具说明文档
# - 在提示词中告知LLM有哪些工具可以调用
# - 自定义Agent时手动构建工具描述
from langchain_core.tools.render import render_text_description
###langchain.tools.render 改为 langchain_core.tools.render

# 构建工具条件和调用描述
rendered_tools = render_text_description([multiply, add, get_current_weather])
print("rendered_tools = ", rendered_tools)

# 构建工具选择器的系统人设
system_prompt = f"""You are an assistant that has access to the following set of tools. Here are the names and descriptions for each tool:
{rendered_tools}
# 构建输入的模板
Given the user input, You can select one of the above tools return the name and input of the tool to use or just response user's content . Return your response as a JSON blob:
"tool": <name of the selected tool>,
"tool_input": <parameters for the selected tool, matching the tool's JSON schema>,
"message": <direct response users content>
"""
# 从LangChain核心模块导入ChatPromptTemplate类
# ChatPromptTemplate用于创建结构化的聊天提示词模板
# 可以定义系统提示、用户消息、AI回复等多角色对话格式
## 主要用途：构建可复用的提示词模板,支持变量插值，动态填充内容,标准化与大语言模型的对话格式
# - 管理多轮对话的消息结构
from langchain_core.prompts import ChatPromptTemplate

# print(system_prompt)
prompt = ChatPromptTemplate.from_messages(
    [("system", system_prompt), ("user", "{input}")]
)
print(prompt)

chain = prompt | qwen
print(chain.invoke({"input": "1+3等于几"}))