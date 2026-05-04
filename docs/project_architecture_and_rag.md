# RoboChain 项目解析与 RAG 说明

## 1. 项目整体定位

这个仓库的核心目标不是做通用聊天，而是把自然语言指令转换成机器人可执行的 Python 代码，并在仿真环境中执行。

系统主链路可以概括为：

1. 用户输入自然语言命令。
2. `gpt_client` 负责构造 Prompt、调用 LLM，并可选接入 RAG。
3. LLM 输出一段 Python 代码。
4. `gpt_client` 通过 ROS2 或 TCP 把这段代码发送给 `gpt_server`。
5. `gpt_server` 从回复中提取代码块并 `exec(...)` 执行。
6. 仿真环境 `demo_env.py` 中定义的机器人原语最终驱动机械臂动作。

这意味着项目本质上是一个“自然语言 -> 代码 -> 仿真执行”的控制系统。

## 2. 目录结构与职责

### 2.1 顶层目录

- `gpt_client/`
  客户端包，负责 Prompt、RAG、LLM 调用、用户交互。
- `gpt_server/`
  服务端包，负责接收 LLM 回复、提取代码、在仿真环境执行。
- `gpt_interface/`
  ROS2 服务接口定义。
- `docs/`
  项目文档与示意图。
- `install/`
  构建后产物和 ROS2 安装脚本。
- `log/`
  构建日志。

### 2.2 `gpt_client` 结构

- `gpt_client/gpt_client/prompts/`
  提示词资源。
  - `system.txt`：约束模型只能输出可执行 Python 代码，不能虚构函数。
  - `scene.txt`：场景描述，例如工作台上有哪些方块。
  - `primitives.txt`：允许调用的机器人原语接口说明。
  - `task_settings.txt`：任务规则说明，也是当前 RAG 唯一检索数据源。
  - `prompt_template.py`：把上述文本拼成 Prompt 模板。

- `gpt_client/gpt_client/commons/`
  公共工具。
  - `utils.py`：配置加载、终端打印。
  - `embedding_utils.py`：文档切块、embedding 初始化、向量库初始化。

- `gpt_client/gpt_client/agents/`
  对话链封装。
  - `base_memory.py`：纯 memory 对话。
  - `base_retrieval.py`：纯 RAG。
  - `base_memory_retrieval.py`：RAG + memory。

- `gpt_client/gpt_client/examples/`
  实际运行入口。
  - `client_retrieval_gpt.py`：ROS2 + RAG。
  - `client_tcp_retrieval_gpt.py`：TCP + RAG。
  - `client_memory.py`：ROS2 + memory。
  - 其余脚本主要是不同模型或测试变体。

### 2.3 `gpt_server` 结构

- `gpt_server/gpt_server/gpt_server.py`
  ROS2 服务端。接收 `GPT.srv` 请求，提取代码并在仿真环境执行。

- `gpt_server/gpt_server/gpt_server_tcp.py`
  TCP 服务端。功能和 ROS2 版本类似，但通过 socket 收代码。

- `gpt_server/gpt_server/demo_env.py`
  机器人仿真环境与原语定义，真正可被 LLM 间接调用的动作接口都在这里。

### 2.4 `gpt_interface`

- `gpt_interface/srv/GPT.srv`
  ROS2 服务定义：

```srv
string data
---
bool res
```

客户端把 LLM 输出的文本发送给服务端，服务端返回是否成功提取到代码。

## 3. 项目如何控制机器人

### 3.1 用户输入层

当前项目的用户输入入口本质上都是命令行 `input(...)`。

例如：

- `gpt_client/gpt_client/examples/client_retrieval_gpt.py`
- `gpt_client/gpt_client/examples/client_tcp_retrieval_gpt.py`
- `gpt_client/gpt_client/examples/client_memory.py`

这些脚本都会循环读取：

```python
question = input(...)
```

所以项目原生支持的是“文本命令控制”，不是“语音直接控制”。

### 3.2 LLM 生成代码

模型收到 Prompt 后，会根据：

- 系统约束
- 场景信息
- 原语说明
- 可选的 RAG 检索结果

生成一段 Python 代码。

例如模型被要求只调用：

- `pri.move(...)`
- `pri.grab(...)`
- `pri.get_obj_pose(...)`
- `pri.reset_robot()`
- `pri.gripper_ctrl(...)`

这些接口定义来自 `primitives.txt`，实际实现来自 `gpt_server/gpt_server/demo_env.py`。

### 3.3 服务端执行代码

`gpt_server.py` 和 `gpt_server_tcp.py` 都会用正则提取三引号代码块：

```python
```python
...
```
```

提取后执行：

```python
exec(code)
```

因此系统并不是把指令映射到固定动作表，而是让模型实时生成 Python 代码并直接执行。

## 4. 你这个项目里“语音控制”到底怎么用

## 4.1 当前仓库没有现成语音模块

仓库中没有看到以下能力的实现：

- 录音采集
- 语音识别 ASR
- 文本转语音 TTS
- 麦克风实时监听

也没有找到常见语音库依赖，例如：

- `whisper`
- `speech_recognition`
- `pyaudio`
- `vosk`
- `funasr`

所以严格来说，你的项目当前并不具备“开箱即用的语音控制”。

## 4.2 现有架构下如何实现语音控制

如果要用语音控制，正确理解应该是：

1. 先用语音识别把语音转成文本。
2. 把识别出的文本当作 `question` 输入给现有 `gpt_client`。
3. 后续链路完全复用当前系统：
   - 文本 -> LLM/RAG -> Python 代码
   - Python 代码 -> ROS2/TCP -> `gpt_server`
   - `gpt_server` 执行代码 -> 机器人动作

也就是：

`语音 -> ASR -> 文本 -> 现有 client -> LLM/RAG -> server exec -> 机器人`

## 4.3 你现在能实际使用的“语音控制方式”

在不改项目主体架构的前提下，有两种现实可行的方式：

### 方式 A：外部语音转文字，再手动粘贴到终端

最简单，不改代码。

流程：

1. 用系统输入法、手机、讯飞、Windows 语音输入等，把语音转成文字。
2. 把文字粘贴到 `client_retrieval_gpt.py` 或 `client_tcp_retrieval_gpt.py` 的终端输入框。
3. 系统按现有文本流程执行。

### 方式 B：单独写一个 ASR 前端，替换 `input(...)`

这才是工程上更完整的“语音控制”。

做法是新加一个语音前端脚本，不动核心控制链：

1. 麦克风采集音频。
2. ASR 转文字。
3. 把识别结果传给现有 `GPTAssistant.ask(...)`。
4. 返回代码文本后仍按 ROS2/TCP 发给 server。

这类改法本质上只是把“输入设备”从键盘换成麦克风，RAG 和执行层都不用重写。

## 5. RAG 在项目中的真实作用

## 5.1 当前 RAG 的定位

你这里的 RAG 不是通用知识问答，也不是在检索整个代码库。

它的真实作用是：

把任务规则文档 `task_settings.txt` 做成一个小型可检索知识库，在用户提问时检索最相关的规则片段，再把这些规则塞进 Prompt，帮助模型更稳定地生成机器人控制代码。

换句话说，你的 RAG 更像是“规则增强 Prompt”，不是“大知识库检索系统”。

## 5.2 RAG 数据源只有一个文件

当前数据源来自：

- `gpt_client/gpt_client/prompts/task_settings.txt`

`embedding_utils.py` 中的 `load_docs()` 只加载这一个文件：

```python
loader = TextLoader(... "../prompts/task_settings.txt")
```

所以当前 RAG 并不会检索：

- `system.txt`
- `scene.txt`
- `primitives.txt`
- 项目源码
- 外部文档

这点非常关键。

## 5.3 文档如何切块

在 `gpt_client/gpt_client/commons/embedding_utils.py` 中：

```python
text_splitter = CharacterTextSplitter(
    separator="---",
    chunk_size=500,
    chunk_overlap=20
)
```

这表示：

- 按 `---` 分段
- 每块最大约 500 字符
- 相邻块重叠 20 字符

而你的 `task_settings.txt` 本身就是按 `---` 分成几段规则，所以这个切法是有意图的。

## 5.4 向量模型怎么选

`embedding_utils.py` 里有两个开关：

```python
EMBEDDING_MODEL = 1
VECTOR_STORE = 1
```

当前配置代表：

- `EMBEDDING_MODEL = 1`
  使用 HuggingFace embedding。
- `VECTOR_STORE = 1`
  使用 Chroma 向量库。

对应逻辑：

- `EMBEDDING_MODEL == 0`：OpenAIEmbeddings
- `EMBEDDING_MODEL == 1`：HuggingFaceEmbeddings

默认 embedding 模型是：

```python
'flax-sentence-embeddings/all_datasets_v4_MiniLM-L6'
```

## 5.5 向量库怎么建

### Pinecone 分支

如果 `VECTOR_STORE == 0`，就走 Pinecone。

特点：

- 需要 `PINECONE_API_KEY`
- 支持已有索引复用
- `is_already_indexed` 在这个分支有效

### Chroma 分支

你当前实际走的是 Chroma：

```python
vector_store = Chroma.from_documents(docs, embedding_model)
```

这意味着：

- 启动时直接根据 `docs` 建一个向量库
- 没有指定持久化目录
- 每次启动大概率都会重新构建
- `is_already_indexed` 参数在 Chroma 分支里实际上没有发挥作用

所以你当前的 RAG 更像“运行时临时索引”，不是长期维护的知识库。

## 5.6 检索是在什么地方发生的

### 纯 RAG 模式

`client_retrieval_gpt.py` 和 `base_retrieval.py` 使用：

```python
RetrievalQA.from_chain_type(...)
```

并把 retriever 设置为：

```python
vector_store.as_retriever(search_kwargs={'k': 3})
```

也就是：

- 每次提问都检索最相关的 3 个 chunk
- 这 3 段文本会作为 `context` 放进 Prompt

### RAG + 记忆模式

`base_memory_retrieval.py` 使用：

```python
ConversationalRetrievalChain.from_llm(...)
```

在这个模式下：

- 会保留聊天历史
- 会结合上下文理解当前问题
- 再去向量库检索
- 再把检索结果拼到最终 Prompt 中

这是比纯 `RetrievalQA` 更接近对话机器人的用法。

## 5.7 检索结果如何进入 Prompt

在 `prompt_template.py` 中，RAG 用的是 `QA_TEMPLATE` 或 `QA_TEMPLATE_BAICHUAN`。

这两个模板里最关键的占位符是：

```python
{context}
```

LangChain 会把检索到的文本块填到这个位置。

所以模型实际看到的是：

1. `system.txt` 的系统约束
2. `scene.txt` 的场景描述
3. `primitives.txt` 的工具说明
4. RAG 检索出的 `task_settings.txt` 片段
5. 用户当前问题

模型据此生成代码。

## 5.8 你的 RAG 为什么有用

它的主要价值不是提供新知识，而是降低模型在任务规则上的偏差。

例如 `task_settings.txt` 中写了：

- 抓取后应复位
- 放置前要先算目标位姿
- 单位是米
- “向上/上方”意味着 z 轴正方向
- pose 由位置和四元数组成

这些内容并不是每次都必须全部塞进 Prompt。RAG 的作用是只在当前问题相关时取出最相关的几段，减少 Prompt 冗余，同时保留规则约束。

## 5.9 你当前 RAG 的局限

### 1. 数据源太单一

只检索 `task_settings.txt`，覆盖面有限。

### 2. 没有代码知识检索

模型并不会通过 RAG 学到 `demo_env.py` 的真实实现细节，它主要依赖 `primitives.txt` 里的接口说明。

### 3. Chroma 未持久化

每次启动都重建，索引生命周期短，不适合后续扩展大型知识库。

### 4. 检索结果不可见性较强

当前业务代码虽然设置了 `verbose=True`，但整体上仍不够直观，不方便直接观察“这次到底召回了哪几个 chunk”。

### 5. 最终执行风险高

即使 RAG 召回了正确规则，最终服务端仍然是 `exec(code)`。因此一旦模型输出不安全或不合法代码，风险并不会被 RAG 根本消除。

## 6. 三种运行模式的理解

## 6.1 `memory` 模式

代表文件：

- `gpt_client/gpt_client/agents/base_memory.py`
- `gpt_client/gpt_client/examples/client_memory.py`

特点：

- 不做向量检索
- 只靠 Prompt + 对话历史
- 长对话下上下文会越来越长

## 6.2 `retrieval` 模式

代表文件：

- `gpt_client/gpt_client/agents/base_retrieval.py`
- `gpt_client/gpt_client/examples/client_retrieval_gpt.py`
- `gpt_client/gpt_client/examples/client_tcp_retrieval_gpt.py`

特点：

- 使用向量检索
- 不保留显式对话记忆
- 适合基于规则文档的单轮或弱多轮控制

## 6.3 `memory + retrieval` 模式

代表文件：

- `gpt_client/gpt_client/agents/base_memory_retrieval.py`

特点：

- 同时保留历史对话和规则检索
- 是最接近完整 Assistant 的组织方式
- 但当前示例入口并没有把它作为默认控制脚本

## 7. 如果你的目标是“真正的语音控制机器人”

建议按下面的工程拆分理解：

### 最小闭环

1. ASR 负责把语音变成文本。
2. 当前 `gpt_client` 继续负责 Prompt/RAG/LLM。
3. 当前 `gpt_server` 继续负责执行代码。

这样改动最小，也最符合你现有工程。

### 不建议的理解

不要把“语音控制”理解成要重写机器人控制逻辑。你的机器人控制主逻辑已经存在，缺的是一个语音输入前端，而不是控制后端。

## 8. 结论

### 8.1 这个项目本质上是什么

它是一个基于 Prompt 工程和 LangChain 的机器人代码生成执行系统，不是一个纯聊天系统。

### 8.2 语音控制在当前项目里的真实状态

当前没有原生语音模块。要实现语音控制，需要把语音先转换成文本，再走你已经写好的文本控制链路。

### 8.3 RAG 在当前项目里的真实作用

RAG 的核心作用是从 `task_settings.txt` 中检索与当前任务最相关的规则片段，增强 Prompt，帮助模型更稳定地生成符合任务约束的机器人控制代码。

### 8.4 你现在最该清楚的一点

你的项目当前不是“模型直接懂机器人”，而是：

- Prompt 告诉模型场景与可用原语
- RAG 告诉模型当前任务规则
- 模型生成 Python 代码
- 服务端执行代码

这才是系统真正的工作方式。
