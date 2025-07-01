import io
import hashlib
import time
from flask import jsonify
from flask_login import UserMixin
import mysql.connector
from PIL import Image
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length
from flask_wtf import FlaskForm
import os
import configparser

config = configparser.ConfigParser()
# 读取配置文件, 先获取当前文件的绝对路径，然后获取当前文件的目录路径
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
config.read(config_path)
# MySQL配置
DB_CONFIG = dict(config["DB_CONFIG"])
IMG_PER_PG = int(dict(config["IMAGE"])["per_page"])
TOP_K = int(dict(config["IMAGE"])["top_k"])
TOP_P = float(dict(config["IMAGE"])["top_p"])
IMAGE_EXTENSIONS = [
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".PNG",
    ".JPG",
    ".JPEG",
    ".WEBP",
    ".BMP",
]
try:
    conn = mysql.connector.connect(**DB_CONFIG)
    conn.close()
except mysql.connector.Error as err:
    print(f"Error: {err}")
    print("请检查数据库配置是否正确")
    exit(1)


# 用户表单
class LoginForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=1, max=25)]
    )
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")


# 用户类
class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash


class MImage:
    def __init__(self, filehash, tags, id, like=False):
        self.filehash = filehash
        self.tags = tags
        self.id = id
        self.like = like


def cached_response(response, seconds=3600 * 24):
    response.headers["Cache-Control"] = f"public, max-age={seconds}"  # 设置缓存时间
    return response


def is_phone(request):
    user_agent = request.headers.get("User-Agent", "").lower()
    # 检查用户代理中是否包含常见的手机标识
    mobile_agents = [
        "iphone",
        "ipad",
        "android",
        "mobile",
        "blackberry",
        "windows phone",
        "opera mini",
        "opera mobi",
    ]
    return any(agent in user_agent for agent in mobile_agents)


def ImageResizer(image_path, max_width=350, max_height=350, quality=85):
    """
    生成 WebP 格式的缩略图，自动处理透明度和优化压缩。

    参数:
        image_path (str): 原始图片路径
        max_width (int): 最大宽度
        max_height (int): 最大高度
        quality (int): WebP 压缩质量 (1-100)

    返回:
        (io.BytesIO, str): 图片二进制流和 MIME 类型
    """
    with Image.open(image_path) as img:
        # 计算缩放比例
        width, height = img.size
        ratio = min(max_width / width, max_height / height)
        new_width = int(width * ratio)
        new_height = int(height * ratio)

        # 高质量缩放
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # 检查透明度
        has_transparency = img.mode in ("RGBA", "LA") or (
            img.mode == "P" and "transparency" in img.info
        )

        # 转换为 WebP 兼容模式
        if has_transparency:
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

        # 生成 WebP 二进制流
        img_io = io.BytesIO()
        img.save(
            img_io,
            "WEBP",
            quality=quality,
            method=6,  # 压缩方法 (0=fast, 6=slow but best)
            lossless=False,  # 启用有损压缩以减小体积
        )
        img_io.seek(0)

        return img_io, "image/webp"


def get_cache_image_path(image_hash, max_width=500, max_height=500):
    # 生成缩略图路径（格式: thumbs/1e/5c/1e5cxxxxxx.webp）
    if len(image_hash) < 4:
        return None
    thumb_dir = os.path.join(
        "static", "imgs", "thumbs", image_hash[:2], image_hash[2:4]
    )
    thumb_path = os.path.join(thumb_dir, f"{image_hash}.webp")

    # 如果缩略图已存在，直接发送
    if os.path.exists(thumb_path):
        return thumb_path

    # 缩略图不存在，生成并保存
    file_path = get_image_path_by_hash(image_hash)
    if not file_path:
        return None

    # 生成缩略图（建议用Pillow直接保存为WebP）
    from PIL import Image

    img = Image.open(file_path)
    img.thumbnail((max_width, max_height))

    # 确保目录存在
    os.makedirs(thumb_dir, exist_ok=True)

    # 保存为WebP（优化质量/大小）
    img.save(thumb_path, "WEBP", quality=95)

    return thumb_path


def get_image_path_by_id(image_id):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    query = "SELECT filepath FROM image WHERE id = %s"
    cursor.execute(query, (image_id,))
    return cursor.fetchone()[0]  # 返回图片路径


def get_image_hash_by_id(image_id):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    query = "SELECT hash FROM image WHERE id = %s"
    cursor.execute(query, (str(image_id),))
    # 如果没有找到图片，返回None
    result = cursor.fetchone()
    res = result[0] if result else None
    conn.close()
    cursor.close()
    return res  # 返回图片hash


def calculate_image_hash(image_id):
    hash_object = hashlib.md5(str(image_id).encode())
    return hash_object.hexdigest()


def get_gallery_images_count(gallery_name):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    query = "SELECT COUNT(*) FROM gallery_image gi JOIN gallery g on gi.gallery_id = g.id WHERE g.name = %s"
    cursor.execute(query, (gallery_name,))
    result = cursor.fetchone()
    conn.close()
    return result[0]


def get_gallery_images(gallery_name, page, uid, per_page=30):
    offset = (page - 1) * per_page
    with mysql.connector.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cursor:
            query = """
                SELECT 
                    i.hash, 
                    i.id,
                    (SELECT GROUP_CONCAT(t.name) FROM tag t 
                     JOIN image_tag it ON t.id = it.tag_id 
                     WHERE it.image_id = i.id) AS tags,
                    EXISTS (SELECT 1 FROM user_liked ul 
                            WHERE ul.image_id = i.id AND ul.uid = %s) AS liked
                FROM image i 
                JOIN gallery_image gi ON i.id = gi.image_id 
                JOIN gallery g ON gi.gallery_id = g.id 
                WHERE g.name = %s 
                LIMIT %s OFFSET %s
            """
            cursor.execute(query, (uid, gallery_name, per_page, offset))
            results = cursor.fetchall()

    images = []
    for row in results:
        tags = row[2].split(",") if row[2] else []
        images.append(MImage(filehash=row[0], tags=tags, id=row[1], like=row[3]))
    return images


def isGalleyExist(gallery_name):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    query = "SELECT i.hash FROM image i JOIN gallery_image gi on i.id = gi.image_id JOIN gallery g on gi.gallery_id = g.id WHERE g.name = %s LIMIT 1"
    cursor.execute(query, (gallery_name,))
    result = cursor.fetchone()
    conn.close()
    if not result:
        return False
    return os.path.exists(get_image_path_by_hash(result[0]))


def get_all_galleries() -> list[str]:
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    query = "SELECT name FROM gallery"
    cursor.execute(query)
    results = cursor.fetchall()
    conn.close()
    gals = [row[0] for row in results if isGalleyExist(row[0])]
    gals.sort()
    print(f"galleries: {gals}")
    return gals


def get_galleries_count():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    query = "SELECT COUNT(*) FROM gallery"
    cursor.execute(query)
    result = cursor.fetchone()
    conn.close()
    return result[0]


def get_image_path_by_hash(image_hash):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    query = "SELECT filepath FROM image WHERE hash = %s"
    cursor.execute(query, (image_hash,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def get_image_tags(image_hash):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    query = """
    SELECT tag.name
    FROM tag
    JOIN image_tag ON tag.id = image_tag.tag_id
    JOIN image ON image_tag.image_id = image.id
    WHERE image.hash = %s
    """
    cursor.execute(query, (image_hash,))
    tags = [row[0] for row in cursor.fetchall()]
    tags.sort()
    conn.close()
    return tags


# 搜索图片函数
def search_images_by_tags(tags, exact_match):
    global EXACTMATCH
    EXACTMATCH = exact_match
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    start_time = time.time()
    print(f"searching for tags: {tags}")
    if exact_match:
        # 精确匹配标签
        placeholders = ", ".join(["%s"] * len(tags))  # 为每个标签生成占位符
        query = f"""
        SELECT image.id, image.filepath
        FROM image
        JOIN image_tag ON image.id = image_tag.image_id
        JOIN tag ON image_tag.tag_id = tag.id
        WHERE tag.name IN ({placeholders})
        GROUP BY image.id
        HAVING COUNT(DISTINCT tag.id) = %s ORDER BY image.id;
        """
        cursor.execute(query, (*tags, len(tags)))
        print("exact match")

    else:
        # 使用方案一修改后的代码
        exists_clauses = []
        like_patterns = []
        for tag in tags:
            exists_clauses.append(
                f"""
                EXISTS (
                    SELECT 1
                    FROM image_tag
                    JOIN tag ON image_tag.tag_id = tag.id
                    WHERE image.id = image_tag.image_id
                    AND tag.name LIKE %s
                )
            """
            )
            like_patterns.append(f"%{tag}%")

        query = f"""
            SELECT DISTINCT image.id, image.filepath
            FROM image
            WHERE {' AND '.join(exists_clauses)}
            ORDER BY image.id;
        """
        # print(query)
        cursor.execute(query, like_patterns)
        print("fuzzy match")

    # 获取查询结果
    results = cursor.fetchall()
    print(f"\n查询执行时间:{time.time()-start_time}")

    conn.close()
    # print("找到结果 ", len(results))
    return [calculate_image_hash(row[1]) for row in results if os.path.exists(row[1])]


def get_image_id_by_hash(image_hash):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    query = "SELECT id FROM image WHERE hash = %s"
    cursor.execute(query, (image_hash,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def remove_tag_from_image(image_id, tag):
    # Connect to database
    with mysql.connector.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cursor:
            try:
                # Check if the tag exists
                cursor.execute("SELECT id FROM tag WHERE name = %s", (tag,))
                tag_result = cursor.fetchone()

                if not tag_result:
                    return jsonify({"success": False, "message": "Tag not found"})

                tag_id = tag_result[0]

                # Remove the image_tag relationship
                cursor.execute(
                    "DELETE FROM image_tag WHERE tag_id = %s AND image_id = %s",
                    (tag_id, image_id),
                )
                # Check if the tag is still in use
                print("checking if tag is still in use")
                cursor.execute(
                    "SELECT 1 FROM image_tag WHERE tag_id = %s LIMIT 1", (tag_id,)
                )
                tag_in_use = cursor.fetchone()
                if not tag_in_use:
                    # Tag is not in use, delete it
                    cursor.execute("DELETE FROM tag WHERE id = %s", (tag_id,))
                    # adjust auto increment, set to max(id) + 1
                    cursor.execute("SELECT MAX(id) FROM tag")
                    max_id = cursor.fetchone()[0]
                    cursor.execute(f"ALTER TABLE tag AUTO_INCREMENT = {max_id + 1}")
                conn.commit()

                return jsonify({"success": True})

            except Exception as e:
                print(f"Error: {e}")
                return jsonify({"success": False, "message": str(e)})


def add_tag_to_image(image_id, tag):
    # Connect to database
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    try:
        # Check if the tag exists
        print("checking tag")
        cursor.execute("SELECT id FROM tag WHERE name = %s", (tag,))
        tag_result = cursor.fetchone()

        if not tag_result:
            # Tag doesn't exist, insert new tag
            print("tag doesn't exist")
            cursor.execute("INSERT INTO tag (name) VALUES (%s)", (tag,))
            conn.commit()
            tag_id = cursor.lastrowid  # Get the new tag ID
        else:
            print("tag exists")
            tag_id = tag_result[0]  # Use existing tag ID

        # Insert or update the image_tag relationship
        cursor.execute(
            "SELECT 1 FROM image_tag WHERE tag_id = %s AND image_id = %s",
            (tag_id, image_id),
        )
        image_tag_result = cursor.fetchone()

        if not image_tag_result:
            cursor.execute(
                "INSERT INTO image_tag (tag_id, image_id) VALUES (%s, %s)",
                (tag_id, image_id),
            )
            conn.commit()
        else:
            return jsonify({"success": False, "duplicate": True})

        return jsonify({"success": True})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"success": False, "message": str(e)})

    finally:
        cursor.close()
        conn.close()


def is_user_like(image_id, uid):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    query = "SELECT 1 FROM user_liked WHERE image_id = %s AND uid = %s"
    cursor.execute(query, (image_id, uid))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def toggle_like_image(image_id, uid):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    query = "SELECT 1 FROM user_liked WHERE image_id = %s AND uid = %s"
    cursor.execute(query, (image_id, uid))
    result = cursor.fetchone()
    if result:
        cursor.execute(
            "DELETE FROM user_liked WHERE image_id = %s AND uid = %s", (image_id, uid)
        )
    else:
        cursor.execute(
            "INSERT INTO user_liked (image_id, uid) VALUES (%s, %s)", (image_id, uid)
        )
    conn.commit()
    conn.close()
    print("like toggled")
    return jsonify({"success": True})


def fetch_users():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT uid, username, password_hash FROM user")
    results = cursor.fetchall()
    conn.close()
    return [User(*row) for row in results]


def fetch_user_liked(uid):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    query = """
        SELECT i.hash, i.id
        FROM user_liked ul
        JOIN image i ON ul.image_id = i.id
        WHERE ul.uid = %s
        ORDER BY i.id
    """
    cursor.execute(query, (uid,))
    results = cursor.fetchall()
    conn.close()
    return [MImage(row[0], get_image_tags(row[0]), row[1], True) for row in results]


def fetch_user(username):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    query = "SELECT uid, username, password_hash FROM user WHERE username = %s"
    cursor.execute(query, (username,))
    result = cursor.fetchone()
    conn.close()
    return {"id": result[0], "username": result[1]}


def remove_user_from_db(user_id):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user WHERE uid = %s", (user_id,))
    if not cursor.fetchone():
        conn.close()
        return False
    cursor.execute("DELETE FROM user WHERE uid = %s", (user_id,))
    conn.commit()
    conn.close()
    return True
