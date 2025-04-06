import os
import mysql.connector
import hashlib
from tqdm import tqdm

# 定义图片文件夹路径列表
PATHS = ["/home/ming/Pictures/pixabay_images"]

# MySQL数据库配置
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "password",
    "database": "picSearcher",
}

# 连接到MySQL数据库
conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()


def get_tags():
    tags = set()
    for path in PATHS:
        for root, dirs, files in os.walk(path):
            for filename in files:
                if (
                    filename.endswith(".jpg")
                    or filename.endswith(".png")
                    or filename.endswith(".JPG")
                    or filename.endswith(".PNG")
                    or filename.endswith(".jpeg")
                    or filename.endswith(".JPEG")
                ):
                    # 获取图片的绝对路径
                    absolute_path = os.path.abspath(os.path.join(root, filename))

                    # 对应的标签文件路径
                    tag_root = os.path.join(root, "tags")
                    tag_file = os.path.join(
                        tag_root,
                        filename.replace(".jpg", ".txt")
                        .replace(".png", ".txt")
                        .replace(".JPG", ".txt")
                        .replace(".PNG", ".txt")
                        .replace(".jpeg", ".txt")
                        .replace(".JPEG", ".txt"),
                    )

                    if os.path.exists(tag_file):
                        with open(tag_file, "r") as f:
                            for tag in f.read().split(", "):
                                tags.add(tag.strip())

    print(len(tags))

    return tags


# 初始化数据库和表


def calculate_image_hash(image_path):
    hash_object = hashlib.md5(str(image_path).encode())
    return hash_object.hexdigest()


def import_images_with_tags(tags: list[str]):
    # 插入标签到 tags 表
    for tag in tags:
        cursor.execute("SELECT id FROM tag WHERE name = %s", (tag.strip(),))
        result = cursor.fetchone()
        # 如果标签不存在，则插入
        if not result:
            cursor.execute("INSERT IGNORE INTO tag (name) VALUES (%s)", (tag.strip(),))

    # 获取标签和对应的 ID
    cursor.execute("SELECT id, name FROM tag")
    tag_map = {name: id for id, name in cursor.fetchall()}

    for image_folder in PATHS:
        for root, dirs, files in os.walk(image_folder):
            first = True
            gallery_id = None
            for filename in tqdm(files, unit="pics"):
                if (
                    filename.endswith(".jpg")
                    or filename.endswith(".png")
                    or filename.endswith(".JPG")
                    or filename.endswith(".PNG")
                    or filename.endswith(".jpeg")
                    or filename.endswith(".JPEG")
                ):
                    # 获取图片的绝对路径
                    absolute_path = os.path.abspath(os.path.join(root, filename))
                    # 只在第一次插入相册
                    if first:
                        gallery_name = absolute_path.split("/")[-2]
                        cursor.execute(
                            "SELECT id FROM gallery WHERE name = %s", (gallery_name,)
                        )
                        res = cursor.fetchone()
                        if res:
                            tqdm.write(f"gallery {gallery_name} already exists!")
                            gallery_id = res[0]
                        else:
                            tqdm.write(f"inserting gallery: {gallery_name}")
                            # 插入相册到 gallery 表
                            cursor.execute(
                                "INSERT IGNORE INTO gallery (name) VALUES (%s)",
                                (gallery_name,),
                            )
                            gallery_id = cursor.lastrowid
                        first = False
                    # 对应的标签文件路径
                    tag_root = os.path.join(root, "tags")
                    tag_file = os.path.join(
                        tag_root,
                        filename.replace(".jpg", ".txt")
                        .replace(".png", ".txt")
                        .replace(".JPG", ".txt")
                        .replace(".PNG", ".txt")
                        .replace(".jpeg", ".txt")
                        .replace(".JPEG", ".txt"),
                    )

                    # 检查图片是否已经存在于数据库中
                    cursor.execute(
                        "SELECT id FROM image WHERE filepath = %s", (absolute_path,)
                    )
                    result = cursor.fetchone()

                    if result:
                        # 如果图片已存在，则跳过插入
                        print(
                            f"Image {absolute_path} already exists with id {result[0]}. Skipping..."
                        )
                        continue

                    if os.path.exists(tag_file):
                        with open(tag_file, "r") as f:
                            image_tags = f.read().strip().split(", ")

                        # 插入图片路径到 images 表
                        cursor.execute(
                            "INSERT INTO image (filepath, hash) VALUES (%s, %s)",
                            (absolute_path, calculate_image_hash(absolute_path)),
                        )
                        image_id = cursor.lastrowid
                        # print(f"inserting picture {absolute_path}")
                        # print(
                        #     f"constrcting gallery {gallery_name} where {gallery_id}:{absolute_path},{image_id}"
                        # )
                        cursor.execute(
                            "INSERT INTO gallery_image (image_id, gallery_id) VALUES (%s, %s)",
                            (image_id, gallery_id),
                        )
                        # 插入关联的标签到 image_tags 表
                        for tag in image_tags:
                            tag_id = tag_map.get(tag.strip())
                            if tag_id:
                                cursor.execute(
                                    "INSERT INTO image_tag (image_id, tag_id) VALUES (%s, %s)",
                                    (image_id, tag_id),
                                )

    conn.commit()


if __name__ == "__main__":
    tags = get_tags()
    import_images_with_tags(tags)
cursor.close()
conn.close()
