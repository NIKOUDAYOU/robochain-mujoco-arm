import os
import sys
import logging

import rclpy
from rclpy.node import Node
from gpt_interface.srv import GPT
from langchain_community.chat_models import ChatZhipuAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain.chains import RetrievalQA
from langchain_openai import ChatOpenAI

sys.path.append(os.path.join(os.path.dirname(__file__), '../../..'))
from gpt_client.prompts.prompt_template import QA_TEMPLATE_BAICHUAN
import gpt_client.commons.embedding_utils as eu
from gpt_client.commons.utils import *

logging.basicConfig(level=logging.INFO)

# 这个脚本是一个基于 ROS2 的 RAG 客户端示例。
# 它负责把“用户文本指令 -> RAG 检索增强 -> LLM 输出 -> 发送给服务端执行”
# 这条链路串起来。


class GPTAssistant:
    """负责初始化大模型和 RAG 检索链，并提供问答接口。"""

    def __init__(self, verbose=False) -> None:

        logging.info("Loading keys...")
        # 从本地配置文件中读取环境变量，例如 API Key。
        cfg_file = os.path.join(os.path.dirname(__file__), '../commons/config.json')
        set_global_configs(cfg_file)
        logging.info(f"Done.")

        logging.info("Initialize LLM...")
        # 初始化智谱模型作为主 LLM。
        # 它的职责是结合 prompt 和检索结果生成最终回答。
        llm = ChatZhipuAI(
            model="glm-4",
            temperature=0.5,
            max_tokens=2048,
            zhipuai_api_base="https://open.bigmodel.cn/api/paas/v4/chat/completions",
            zhipuai_api_key="ea014227309598e3e5316b060fde1318.m8PmgfsFYHyxcXbd"
        )
        logging.info(f"Done.")

        logging.info("Initialize tools...")
        # 初始化 embedding 模型与向量库。
        # 当前检索语料主要来自 prompts/task_settings.txt。
        embedding_model = eu.init_embedding_model()
        vector_store = eu.init_vector_store(embedding_model)
        logging.info(f"Done.")

        logging.info("Initialize chain...")
        # prompt 决定检索到的 context 如何参与最终生成。
        chain_type_kwargs = {"prompt": QA_TEMPLATE_BAICHUAN, "verbose": verbose}

        # RetrievalQA 的工作流程：
        # 1. 把用户问题交给 retriever
        # 2. 从向量库中找出最相关的文档块
        # 3. 将这些文档块拼到 prompt 的 context 中
        # 4. 交给 LLM 生成结果
        self.conversation = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type='stuff',
            # k=3 表示 top-k 检索，这里每次取最相关的 3 个 chunk。
            retriever=vector_store.as_retriever(search_kwargs={'k': 3}),
            chain_type_kwargs=chain_type_kwargs,
            return_source_documents=True
        )
        logging.info(f"Done.")

        os.system("clear")
        streaming_print_banner()

    def ask(self, question):
        # 执行一轮完整的 RAG 问答流程，并返回文本结果。
        result_dict = self.conversation(question)
        result = result_dict['result']
        return result


class GPTClient(Node):
    """ROS2 客户端节点。

    参数说明：
    - node_name(str): ROS2 节点名称
    - is_debug(bool): 为 True 时只在本地生成回答，不向服务端发送
    - verbose(bool): 是否打印 LangChain 的详细链路日志
    """

    def __init__(self, node_name: str, is_debug: bool = False, verbose=False) -> None:
        super().__init__(node_name)
        self.get_logger().info("%s already." % node_name)

        # 创建到 gpt_service 的 ROS2 客户端，用于把模型输出发给服务端。
        self.gpt_client = self.create_client(GPT, "gpt_service")

        self.is_debug = is_debug
        if not self.is_debug:
            # 非调试模式下，启动后会一直等待服务端上线。
            while not self.gpt_client.wait_for_service(timeout_sec=1.0):
                self.get_logger().warn('Waiting for the server to go online...')

        self.gpt = GPTAssistant(
            verbose=verbose,
        )

    def result_callback(self, result):
        # 保留异步回调接口，目前没有对返回结果做额外处理。
        response = result.result()

    def send_msg(self, msg):
        """把 LLM 生成的结果发送给 ROS2 服务端。"""

        request = GPT.Request()
        request.data = msg
        self.gpt_client.call_async(request).add_done_callback(self.result_callback)

    def ask(self, question):
        # 对外统一暴露问答接口，底层调用 GPTAssistant 的 RAG 链。
        return self.gpt.ask(question)


def main(args=None):
    # 初始化 ROS2 运行环境。
    rclpy.init(args=args)
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    gpt_node = GPTClient(
        "gpt_client",
        is_debug=False,
        verbose=True
    )

    while rclpy.ok():
        question = input(colors.YELLOW + "User> " + colors.ENDC)
        if question == "!quit" or question == "!exit":
            break
        if question == "!clear":
            os.system("clear")
            continue

        # 先通过 RAG 链生成回答，再输出到终端。
        result = gpt_node.ask(question)
        print(colors.GREEN + "Assistant> " + colors.ENDC + f"{result}")
        if not gpt_node.is_debug:
            # 非调试模式下，把模型输出再发给服务端执行。
            gpt_node.send_msg(result)

    gpt_node.destroy_node()
    rclpy.shutdown()
