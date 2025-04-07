import sqlite3
import os
from PIL import Image
import numpy as np
import torch
import faiss
import mysql.connector
from multilingual_clip import pt_multilingual_clip
import transformers
import open_clip

text_model_name = "M-CLIP/XLM-Roberta-Large-Vit-B-16Plus"
text_model_path = "./hf-mirror/hub/models--openai--clip-vit-base-patch32/snapshots"
device = "cuda" if torch.cuda.is_available() else "cpu"


def init_models():
    text_model = pt_multilingual_clip.MultilingualCLIP.from_pretrained(
        "M-CLIP/XLM-Roberta-Large-Vit-B-16Plus"
    )
    tokenizer = transformers.AutoTokenizer.from_pretrained(
        "M-CLIP/XLM-Roberta-Large-Vit-B-16Plus"
    )
    return text_model, tokenizer


# text_model = pt_multilingual_clip.MultilingualCLIP.from_pretrained(text_model_name)

# tokenizer = transformers.AutoTokenizer.from_pretrained(text_model_name)

# text_model.to(device)


def get_image_path_by_id(image_id):

    query = "SELECT filepath FROM image WHERE id = %s"
    cursor.execute(query, (str(image_id),))
    res = cursor.fetchone()[0]
    return res


def process_and_save_index(uid_list, db_path, index_path):
    # rows = [get_image_path_by_id(uid) for uid in uid_list]
    query = "SELECT id,filepath FROM image"
    cursor.execute(query)
    image_model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-B-16-plus-240", pretrained="laion400m_e32"
    )
    image_model.to(device)

    if cursor.rowcount == 0:
        print("没有查询到对应记录")
        return

    # 构造 uid 到 img_path 的映射
    # uid_to_path = {uid: path for uid, path in zip(uid_list, rows)}
    uid_to_path = {}
    for uid, path in cursor.fetchall():
        uid_to_path[uid] = path
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
            image = Image.open(img_path)

            # 处理调色板图片的透明度
            if image.mode == "P" and "transparency" in image.info:
                # 转换为RGBA并创建白色背景
                image = image.convert("RGBA")
                background = Image.new("RGBA", image.size, (255, 255, 255))
                image = Image.alpha_composite(background, image).convert("RGB")
            else:
                # 否则直接转换为RGB
                image = image.convert("RGB")
        except Exception as e:
            print(f"加载 UID {uid} 对应图片 {img_path} 失败：{e}")
            continue

        # 预处理图片并提取嵌入
        inputs = preprocess(image).unsqueeze(0).to(device)
        with torch.no_grad():
            image_features = image_model.encode_image(inputs)
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

    return processed_uids


def search_by_text(text, index, top_k=20):
    # 使用 tokenizer 生成 tokenized 输入，并转移到相同的设备
    text_model = pt_multilingual_clip.MultilingualCLIP.from_pretrained(
        "M-CLIP/XLM-Roberta-Large-Vit-B-16Plus"
    )
    tokenizer = transformers.AutoTokenizer.from_pretrained(
        "M-CLIP/XLM-Roberta-Large-Vit-B-16Plus"
    )
    with torch.no_grad():
        res = text_model.forward(text, tokenizer).to(device)
    # 将向量转换为 numpy 数组，并提取第一维的向量
    vector = res.cpu().numpy()[0]
    # 对向量进行 L2 归一化（归一化后的向量使用内积可以模拟余弦相似度）
    faiss.normalize_L2(vector.reshape(1, -1))

    # 在 FAISS 索引中搜索最相似的图片
    D, I = index.search(vector.reshape(1, -1), top_k)

    return I[0], D[0]  # 返回索引和分数


if __name__ == "__main__":
    # 示例：处理和保存索引
    import configparser

    config = configparser.ConfigParser()

    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "../config.ini"
    )
    config.read(config_path)
    # MySQL配置
    DB_CONFIG = dict(config["DB_CONFIG"])
    # print(DB_CONFIG)
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    uid_list = [i for i in range(1, 2420)]  # 替换为实际的 UID 列表
    db_path = "image_vector_db.db"  # SQLite 数据库路径
    index_path = "image_vector_db.index"  # FAISS 索引文件路径

    processed_uids = process_and_save_index(uid_list, db_path, index_path)

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

    cursor.close()
    conn.close()
