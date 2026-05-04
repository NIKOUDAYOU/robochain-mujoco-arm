import os
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.document_loaders import TextLoader

# 这个模块负责项目中 RAG 相关的基础能力：
# 1. 读取规则文档
# 2. 将文档切分成适合检索的文本块
# 3. 初始化 embedding 模型，把文本编码成向量
# 4. 初始化向量库，供后续相似度检索使用
#
# 当前项目中，RAG 的主要语料并不是整个代码仓库，
# 而是 `prompts/task_settings.txt` 这份任务规则文件。

EMBEDDING_MODEL = 1  # O for OpenAIEmbeddings and 1 for HuggingFaceEmbeddings
if EMBEDDING_MODEL == 0:
    from langchain_community.embeddings.openai import OpenAIEmbeddings
elif EMBEDDING_MODEL == 1:
    from langchain_community.embeddings import HuggingFaceEmbeddings

VECTOR_STORE = 1  # 0 for Pinecone and 1 for Chroma
if VECTOR_STORE == 0:
    import pinecone
    from langchain_community.vectorstores import Pinecone
elif VECTOR_STORE == 1:
    # make sure you have chromadb on your local machine `pip install chromadb`
    from langchain_community.vectorstores import Chroma


def load_docs():
    """
    加载 RAG 源文档，并把它切分成更小的文本块。

    当前只加载：
    - ../prompts/task_settings.txt

    这样设计的原因是：
    - 这个项目里的 RAG 主要用于检索任务规则和执行约束
    - 而不是拿来检索整个代码仓库或外部知识

    切块策略说明：
    - separator="---"
      task_settings.txt 本身按 `---` 分段，因此优先按段落切分，
      可以尽量保持每条规则的语义完整
    - chunk_size=500
      控制单个 chunk 的长度，避免块太大影响检索精度
    - chunk_overlap=20
      给相邻块保留少量重叠内容，减少边界切分导致的信息丢失

    返回：
    - docs: 切分后的 LangChain Document 列表
    """
    loader = TextLoader(os.path.join(os.path.dirname(__file__), "../prompts/task_settings.txt"))
    documents = loader.load()
    text_splitter = CharacterTextSplitter(separator="---", chunk_size=500, chunk_overlap=20)
    docs = text_splitter.split_documents(documents)
    return docs


def init_embedding_model(model_name = 'flax-sentence-embeddings/all_datasets_v4_MiniLM-L6'):
    """
    初始化 embedding 模型，用于把文本 chunk 转成向量。

    embedding 的作用是：
    - 把文档片段编码成向量
    - 把用户问题也编码成向量
    - 之后通过向量相似度，检索与问题最相关的文档片段

    当前支持两种 embedding 方案：
    - EMBEDDING_MODEL == 0
      使用 OpenAIEmbeddings，需要配置对应 API Key
    - EMBEDDING_MODEL == 1
      使用 HuggingFaceEmbeddings，本地模型方案，当前默认走这条路径

    参数：
    - model_name: HuggingFace embedding 模型名称

    返回：
    - embeddings: 可被 LangChain 向量库使用的 embedding 对象
    """
    if EMBEDDING_MODEL == 0:
        embeddings = OpenAIEmbeddings()  # OpenAI default embedding
    
    elif EMBEDDING_MODEL == 1:
        # 默认放在 CPU 上运行，优点是部署简单；
        # 如果后续有 GPU，也可以把 device 改掉来提升速度。
        embeddings = HuggingFaceEmbeddings(
                        model_name=model_name,
                        model_kwargs={"device": "cpu"},
                    )
    return embeddings

def init_vector_store(embedding_model, is_already_indexed=True):
    """
    初始化向量库，供后续检索器 retriever 使用。

    向量库负责保存文档 chunk 的向量表示，并支持相似度检索。

    当前支持两种后端：
    - VECTOR_STORE == 0: Pinecone
      在线向量数据库，适合做远程持久化索引
    - VECTOR_STORE == 1: Chroma
      本地轻量向量库，适合当前这种小规模规则库

    参数：
    - embedding_model: 已初始化好的 embedding 模型
    - is_already_indexed:
      主要对 Pinecone 分支有意义。
      True 表示尝试复用已有索引；
      False 表示根据当前文档重新构建索引

    返回：
    - vector_store: LangChain 可用的向量库对象
    """
    if VECTOR_STORE == 0:
        vector_store = init_pinecone_vector_store(embedding_model, is_already_indexed)
    elif VECTOR_STORE == 1:
        vector_store = init_chroma_vector_store(embedding_model, is_already_indexed)
    return vector_store

def init_pinecone_vector_store(embedding_model, is_already_indexed=True):
    """
    初始化 Pinecone 向量库。

    这个分支适合在线部署：
    - 文本向量可以本地生成
    - 向量数据保存在 Pinecone
    - 多次运行之间可以复用已有远程索引

    注意：
    - 创建索引时的维度 dimension 必须和 embedding 模型输出维度一致
    - 当前代码写死为 384，是为了匹配默认的 HuggingFace embedding 模型
    """
    pinecone.init(api_key=os.getenv("PINECONE_API_KEY"), environment="us-west4-gcp-free")
    
    index_name = "codellama-vs"
    # 如果索引不存在，就先创建一个新的 Pinecone 索引。
    if index_name not in pinecone.list_indexes():
        # OpenAI 的 text-embedding-ada-002 是 1536 维
        # 当前默认的 HuggingFace 模型是 384 维
        pinecone.create_index(
            name=index_name,
            metric='cosine',
            dimension=384  
        )

    docs = load_docs()

    # 如果还没有建过索引，就根据当前文档创建并上传全部向量。
    if not is_already_indexed:
        vector_store = Pinecone.from_documents(docs, embedding_model, index_name=index_name)
    else:
        # 如果索引已经存在，则直接连接，避免重复上传。
        vector_store = Pinecone.from_existing_index(index_name, embedding_model)
    return vector_store

def init_chroma_vector_store(embedding_model, is_already_indexed=True):
    """
    初始化 Chroma 向量库。

    当前实现里，这个分支会直接根据文档构建一个本地向量库：
    - 没有指定持久化目录
    - 没有显式复用旧索引
    - `is_already_indexed` 参数在这个分支里实际上没有真正起作用

    所以这里的 Chroma 更接近“运行时临时索引”，
    对当前这种小规模规则文件来说已经够用了。
    """
    docs = load_docs()

    # 直接根据文档块构建 Chroma 向量库。
    vector_store = Chroma.from_documents(docs, embedding_model)

    return vector_store
