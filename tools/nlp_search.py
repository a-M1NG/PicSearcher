import sqlite3
import os
from PIL import Image
import numpy as np
import torch
import faiss
from transformers import CLIPProcessor, CLIPModel
import mysql.connector
from multilingual_clip import pt_multilingual_clip
import transformers

model_name = "M-CLIP/XLM-Roberta-Large-Vit-B-16Plus"
model_path = "./hf-mirror/hub/models--openai--clip-vit-base-patch32/snapshots"
model = CLIPModel.from_pretrained(
    os.path.join(model_path, "aa8b329a670ccfc2a5170d7391ac3fca2e88595f")
)
processor = CLIPProcessor.from_pretrained(
    os.path.join(model_path, "3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268")
)
model.to("cuda" if torch.cuda.is_available() else "cpu")


def get_image_path_by_id(image_id):
    import configparser

    config = configparser.ConfigParser()

    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "../config.ini"
    )
    config.read(config_path)
    # MySQL配置
    DB_CONFIG = dict(config["DB_CONFIG"])
    print(DB_CONFIG)
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    query = "SELECT filepath FROM image WHERE id = %s"
    cursor.execute(query, (str(image_id),))
    cursor.close()
    conn.close()
    return cursor.fetchone()[0]


def process_and_save_index(uid_list, db_path, index_path):
    # 连接 SQLite 数据库
    rows = [get_image_path_by_id(uid) for uid in uid_list]

    if not rows:
        print("没有查询到对应记录")
        return

    # 构造 uid 到 img_path 的映射
    uid_to_path = {uid: path for uid, path in zip(uid_list, rows)}

    # 初始化 CLIP 模型和处理器
    # model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
    # processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

    embeddings_list = []
    processed_uids = []  # 记录成功处理的 uid
    from tqdm import tqdm

    # 遍历 uid_list，根据 uid 从映射中获得图片路径，并提取图片嵌入
    for uid in tqdm(uid_list, desc="处理图片", unit="image"):
        if uid not in uid_to_path:
            print(f"UID {uid} 在数据库中没有对应记录")
            continue
        img_path = uid_to_path[uid]
        try:
            image = Image.open(img_path).convert("RGB")
        except Exception as e:
            print(f"加载 UID {uid} 对应图片 {img_path} 失败：{e}")
            continue

        # 预处理图片并提取嵌入
        inputs = processor(images=image, return_tensors="pt")
        with torch.no_grad():
            inputs = {
                k: v.to("cuda" if torch.cuda.is_available() else "cpu")
                for k, v in inputs.items()
            }
            image_features = model.get_image_features(**inputs)
        vector = image_features.cpu().numpy()[0]
        embeddings_list.append(vector)
        processed_uids.append(uid)

    if not embeddings_list:
        print("没有成功处理任何图片")
        return

    # 将嵌入组合成 numpy 数组
    embeddings = np.array(embeddings_list)
    # L2 归一化（使用内积来模拟余弦相似度）
    faiss.normalize_L2(embeddings)

    # 获取向量维度，初始化 FAISS 索引（使用内积作为度量）
    d = embeddings.shape[1]
    index = faiss.IndexFlatIP(d)
    index.add(embeddings)

    print("成功导入图片数量：", index.ntotal)

    # 将 FAISS 索引保存到本地
    faiss.write_index(index, index_path)
    print(f"索引已保存到 {index_path}")

    # 关闭数据库连接
    # conn.close()

    # 返回成功处理的 uid 列表（可选）
    return processed_uids


def search_by_text(text, index, top_k=20):
    """
    根据文本查询相似图片
    :param text: 查询文本
    :param index: FAISS 索引对象
    :param top_k: 返回的最相似图片数量
    :return: 最相似图片的索引和相似度分数
    """

    # processor.to("cuda" if torch.cuda.is_available() else "cpu")
    # 使用 CLIPProcessor 对文本进行预处理
    inputs = processor(text=text, return_tensors="pt")
    # print(inputs)
    # 关闭梯度计算，获取文本向量
    with torch.no_grad():
        inputs = {
            k: v.to("cuda" if torch.cuda.is_available() else "cpu")
            for k, v in inputs.items()
        }
        text_features = model.get_text_features(**inputs)
    # 将向量转换为 numpy 数组，并提取第一维的向量
    vector = text_features.cpu().numpy()[0]
    # 对向量进行 L2 归一化（归一化后的向量使用内积可以模拟余弦相似度）
    faiss.normalize_L2(vector.reshape(1, -1))

    # 在 FAISS 索引中搜索最相似的图片
    D, I = index.search(vector.reshape(1, -1), top_k)

    return I[0], D[0]  # 返回索引和分数


if __name__ == "__main__":
    # 示例：处理和保存索引
    uid_list = [i for i in range(11, 1000)]  # 替换为实际的 UID 列表
    db_path = "image_vector_db.db"  # SQLite 数据库路径
    index_path = "image_vector_db.index"  # FAISS 索引文件路径

    # processed_uids = process_and_save_index(uid_list, db_path, index_path)

    # 加载 FAISS 索引
    index = faiss.read_index(index_path)

    # 测试文本检索
    query_text = "close-up shots of pink flowers"  # 你可以根据需要修改查询文本
    indices, scores = search_by_text(query_text, index)

    # 输出结果
    print(f"查询文本: {query_text}")
    print("最相似图片的索引和分数:")
    for idx, score in zip(indices, scores):
        print(f"索引: {idx}, 分数: {score}")
        print(f"图片路径: {get_image_path_by_id(idx+1)}")
