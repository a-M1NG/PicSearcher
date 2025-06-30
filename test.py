# 检查索引文件

import os
import faiss
from app import add_user_to_db

def check_index_files():
    index_dir = "./"
    if not os.path.exists(index_dir):
        print("索引目录不存在，请先生成索引。")
    else:
        index_files = [f for f in os.listdir(index_dir) if f.endswith(".index")]
        if not index_files:
            print("没有找到索引文件。")
        else:
            print(f"找到 {len(index_files)} 个索引文件：")
            for index_file in index_files:
                print(f"- {index_file}")
                index_path = os.path.join(index_dir, index_file)
                index = faiss.read_index(index_path)
                print(f"索引文件 {index_file} 中包含 {index.ntotal} 个向量。")


def insert_admin():
    add_user_to_db("admin", "passwd")

if __name__ == "__main__":
    # 这里我插入管理员和检查faiss用的，没用
    # check_index_files()