from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
    session,
    abort,
    make_response,
)
from flask_bcrypt import Bcrypt
from flask_login import (
    LoginManager,
    login_user,
    login_required,
    logout_user,
    current_user,
)
import os
from tqdm import trange
from modules import *
from werkzeug.serving import WSGIRequestHandler
import faiss
import torch
import open_clip
import numpy as np
from PIL import Image

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
app = Flask(__name__)
vector_index = faiss.read_index("image_vector_db.index")
from multilingual_clip import pt_multilingual_clip
import transformers

text_model = pt_multilingual_clip.MultilingualCLIP.from_pretrained(
    "M-CLIP/XLM-Roberta-Large-Vit-B-16Plus"
)
tokenizer = transformers.AutoTokenizer.from_pretrained(
    "M-CLIP/XLM-Roberta-Large-Vit-B-16Plus"
)
print("faiss index loaded")
print("ready to perform nlp search")


app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600
app.secret_key = "supersecret"
bcrypt = Bcrypt(app)  # 用于加密密码
login_manager = LoginManager(app)
login_manager.login_view = "login"
HOSTS = ["192.168.137.1", "127.0.0.1", "118.202.40.143"]
ALL_GALLERIES = get_all_galleries()


def search_by_text(text, index, top_k=20, top_p=0.18):
    # 使用 tokenizer 生成 tokenized 输入，并转移到相同的设备
    with torch.no_grad():
        res = text_model.forward(text, tokenizer)
    # 将向量转换为 numpy 数组，并提取第一维的向量
    vector = res.cpu().numpy()[0]
    # 对向量进行 L2 归一化（归一化后的向量使用内积可以模拟余弦相似度）
    faiss.normalize_L2(vector.reshape(1, -1))

    # 在 FAISS 索引中搜索最相似的图片
    D, I = index.search(vector.reshape(1, -1), top_k)
    mask = D[0] >= top_p
    filtered_I = I[0][mask]
    filtered_D = D[0][mask]

    return filtered_I, filtered_D
    # return I[0], D[0]


def faiss_insert(img, id, index):
    pass

def deal_transparent(image):
    if image.mode == "P" and "transparency" in image.info:
                # 转换为RGBA并创建白色背景
                image = image.convert("RGBA")
                background = Image.new("RGBA", image.size, (255, 255, 255))
                image = Image.alpha_composite(background, image).convert("RGB")
    return image


# 用于测试插入
def test_img_insert(img:Image):
    vector_index = faiss.read_index("image_vector_db.index")
    insert_imgs([img], ["test_image"], vector_index)





def insert_imgs(imgs: list, pic_names: list, index: faiss.IndexFlatIP):
    """
    Inserts a batch of images into the FAISS index AND the MySQL DB atomically.
    如果任一步出错，数据库回滚，FAISS 索引恢复到调用前状态。
    
    插入图片到 FAISS 索引和 MySQL 数据库，
    1.imgs 是 PIL Image 对象列表，
    2.pic_names 是图片名称列表。
    3.index 是 向量数据库对象
    """
    # 1. 准备 CLIP 模型和预处理
    image_model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-B-16-plus-240", pretrained="laion400m_e32"
    )
    device = "cuda" if torch.cuda.is_available() else "cpu"
    image_model = image_model.to(device)

    # 校验入参
    if len(imgs) != len(pic_names):
        raise ValueError("Length of imgs and pic_names must be the same.")
    if not imgs:
        print("No images to insert.")
        return

    # 2. 备份旧向量
    old_ntotal = index.ntotal
    if old_ntotal > 0:
        old_vectors = index.reconstruct_n(0, old_ntotal)
    else:
        old_vectors = np.zeros((0, index.d), dtype='float32')

    # 3. 先把所有图片持久化 & DB 条目插入到事务中
    conn = mysql.connector.connect(**DB_CONFIG)
    conn.autocommit = False
    cursor = conn.cursor()
    try:
        # 确保 upload 相册存在
        cursor.execute("SELECT id FROM gallery WHERE name=%s", ("upload",))
        row = cursor.fetchone()
        if row:
            gallery_id = row[0]
        else:
            cursor.execute("INSERT INTO gallery(name) VALUES(%s)", ("upload",))
            gallery_id = cursor.lastrowid

        img_waiting = []
        for img, name in zip(imgs, pic_names):
            pic = name.strip()
            base = dict(config["IMAGE"])["pixabay_images_path"]
            path =os.path.join(base,"upload",f"{pic}.jpg")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            img.save(path, format="JPEG")

            cursor.execute("SELECT id FROM image WHERE filepath=%s", (path,))
            #如果图片已存在，则跳过
            if cursor.fetchone():
                continue

            cursor.execute(
                "INSERT INTO image(filepath, hash) VALUES(%s,%s)",
                (path, calculate_image_hash(path))
            )
            img_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO gallery_image(image_id,gallery_id) VALUES(%s,%s)",
                (img_id, gallery_id)
            )

            # 假设 tag 暂不改动
            img_waiting.append(deal_transparent(img))

        if not img_waiting:
            conn.rollback()
            print("No new images to insert.")
            return

        # 4. 事务先不提交，等待 FAISS 部分也成功
        # -------------- FAISS 部分 ------------------
        # 批量预处理 & 编码
        tensors = [preprocess(im).unsqueeze(0).to(device) for im in img_waiting]
        with torch.no_grad():
            embs = [image_model.encode_image(t).cpu().numpy()[0] for t in tensors]
        embs = np.stack(embs).astype('float32')
        faiss.normalize_L2(embs)

        # 插入到索引
        index.add(embs)
        # -------------------------------------------

        # 5. 全部都成功：提交事务
        conn.commit()
        print(f"Inserted {len(img_waiting)} images into DB and FAISS.")
    except Exception as e:
        # 任意一步出错，都回滚 DB，并把索引吐回原来的状态
        conn.rollback()
        index.reset()
        if old_ntotal > 0:
            index.add(old_vectors)
        print("Error, rolled back DB and FAISS:", e)
    finally:
        faiss.write_index(index,"image_vector_db.index")  # 保存 FAISS 索引
        print("FAISS index saved.")
        cursor.close()
        conn.close()

@app.after_request
def add_cache_headers(response):
    if "static/" in request.path:
        response.cache_control.max_age = 3600
    return response


@login_manager.user_loader
def load_user(user_id):
    conn = mysql.connector.connect(**DB_CONFIG)
    # session.permanent = True
    cursor = conn.cursor()
    cursor.execute(
        "SELECT uid, username, password_hash FROM user WHERE uid = %s", (user_id,)
    )
    user = cursor.fetchone()
    if user:
        return User(id=user[0], username=user[1], password_hash=user[2])
    conn.close()
    return None


# 首页路由
@app.route("/")
def index():
    if session.get("DarkMode") is None:
        session["DarkMode"] = True
    if current_user.is_authenticated:
        return render_template(
            "search.html",
            Username=current_user.username,
            exactmatch=session.get("EXACTMATCH", False),
            nlpsearch=session.get("NLP_MATCH", False),
            darkmode=session.get("DarkMode", True),
        )
    return redirect(
        url_for("login", loginreq=True, darkmode=session.get("DarkMode", True))
    )


latest_results = []
latest_search_tags = ""


# 搜索图片路由
@app.route("/search/", methods=["POST", "GET"])
@login_required
def search():
    global latest_results, latest_search_tags
    session["PHONEUA"] = is_phone(request)

    # 获取当前页码，默认为第1页
    page = request.args.get("page", 1, type=int)
    per_page = IMG_PER_PG  # 每页显示的图片数量，可根据需要调整
    tags = request.args.get("tags", "").strip()
    prev_exact = session.get("EXACTMATCH", False)
    prev_nlp = session.get("NLP_MATCH", False)
    exact_match = "exact_match" in request.args
    nlp_match = "nlp_match" in request.args
    # print(exact_match, nlp_match)
    # nlp_match = "nlp_match" in request.form  # 更简单的检查方式
    # exact_match = "exact_match" in request.form
    session.update({"NLP_MATCH": nlp_match, "EXACTMATCH": exact_match})

    # tags = request.form.get("tags", "").strip()

    if not tags:
        return redirect(url_for("index"))
    if not tags == latest_search_tags or (
        prev_exact != exact_match or prev_nlp != nlp_match
    ):
        if nlp_match:
            print(f"使用自然语言搜索 {tags}")
            try:
                idxs, scores = search_by_text(tags, vector_index, TOP_K, TOP_P)
                latest_results = [get_image_hash_by_id(i + 1) for i in idxs]
                print(
                    f"res: {[(int(idxs[i]),float(scores[i])) for i in range(len(idxs))]}"
                )
            except Exception as e:
                print("自然语言搜索失败，已切换回标签搜索", e)
                session["NLP_MATCH"] = False
                latest_results = search_images_by_tags(tags.split(","), exact_match)
        else:
            latest_results = search_images_by_tags(tags.split(","), exact_match)

        latest_search_tags = tags

    # 分页逻辑
    total_images = len(latest_results)
    total_pages = (total_images + per_page - 1) // per_page  # 计算总页数
    # page = min(page, total_pages)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    images_paginated = latest_results[start_idx:end_idx]  # 获取当前页的图片

    images = [
        MImage(
            image_id,
            get_image_tags(image_id),
            get_image_id_by_hash(image_id),
            is_user_like(get_image_id_by_hash(image_id), current_user.id),
        )
        for image_id in images_paginated
    ]
    if not images:
        return render_template(
            "results.html",
            images=None,  # 传递空的images列表
            Username=current_user.username,
            init_tags=latest_search_tags,
            exactmatch=session.get("EXACTMATCH", False),
            nlpsearch=session.get("NLP_MATCH", False),
            darkmode=session.get("DarkMode", True),
        )

    start_page = max(page - 1, 1)
    end_page = min(page + 1, total_pages)
    # 确保页码不超过总页数
    return render_template(
        "results.html",
        images=images,  # 传递当前页的图片列表
        Username=current_user.username,
        init_tags=latest_search_tags,
        exactmatch=session.get("EXACTMATCH", False),
        phoneua=session.get("PHONEUA", False),
        current_page=page,  # 当前页码
        total_pages=total_pages,  # 总页数
        start_page=start_page,  # 分页的起始页
        end_page=end_page,  # 分页的结束页
        total_count=total_images,  # 总图片数量
        darkmode=session.get("DarkMode", True),
        nlpsearch=session.get("NLP_MATCH", False),
    )


# 图片缩放并展示路由
@app.route("/images/<image_hash>/")
@login_required
def get_image(image_hash):
    thumb_path = get_cache_image_path(image_hash)
    if not thumb_path:
        abort(404)  # 不存在图片
    response = make_response(send_file(thumb_path, mimetype="image/webp"))
    response.cache_control.max_age = 86400 * 30  # 缓存30天
    return response


@app.route("/get_image_tags/<image_hash>/")
def get_image_tags_route(image_hash):
    tags = get_image_tags(image_hash)
    return jsonify({"tags": tags})


# 原图下载路由
@app.route("/original/<image_hash>/", methods=["GET"])
@login_required
def get_original_image(image_hash):
    # 从数据库中根据image_id获取原图路径
    file_path = get_image_path_by_hash(image_hash)
    if not file_path:
        abort(404)
    print("getting original image")
    return send_file(file_path)


@app.route("/gallery/")
@login_required
def gallery():
    page = request.args.get("page", 1, type=int)
    per_page = 12
    galleries = get_galleries(page, per_page)
    total = get_galleries_count()
    total_pages = (total + per_page - 1) // per_page  # 计算总页数
    if page > total_pages:
        # 如果请求的页码超过总页数，重定向到最后一页
        return redirect(url_for("gallery", page=total_pages))
    start_page = max(page - 2, 1)
    end_page = min(page + 2, total_pages)
    return render_template(
        "gallery.html",
        Username=current_user.username,
        init_tags="",
        ingallery=False,
        galleries=galleries,
        phoneua=is_phone(request),
        total_pages=total_pages,
        current_page=page,
        start_page=start_page,
        end_page=end_page,
        nlpsearch=session.get("NLP_MATCH", False),
        exactmatch=session.get("EXACTMATCH", False),
        darkmode=session.get("DarkMode", True),
    )


@app.route("/gallery-<gallery_name>/")
@login_required
def into_gallery(gallery_name):
    if not isGalleyExist(gallery_name):
        abort(404)
    # 获取当前页数，默认是第1页
    current_page = request.args.get("page", 1, type=int)

    # 获取相册图片总数
    total_images = get_gallery_images_count(gallery_name)
    print(f"gallery_name: {gallery_name}, total_images: {total_images}")
    # 每页显示的最大图片数量
    images_per_page = IMG_PER_PG

    # 总页数
    total_pages = (total_images + images_per_page - 1) // images_per_page
    if current_page > total_pages:
        return redirect(
            url_for("into_gallery", gallery_name=gallery_name, page=total_pages)
        )
    if total_images % images_per_page == 0:
        total_pages = max(total_pages - 1, 1)
    print(total_pages)

    # 分页查询获取当前页的图片
    images = get_gallery_images(
        gallery_name, current_page, current_user.id, images_per_page
    )

    # 计算分页的范围
    start_page = max(current_page - 1, 1)
    end_page = min(current_page + 1, total_pages)

    return render_template(
        "gallery.html",
        Username=current_user.username,
        gallery_name=gallery_name,
        ingallery=True,
        init_tags="",
        images=images,
        current_page=current_page,
        total_pages=total_pages,
        start_page=start_page,
        end_page=end_page,
        phoneua=is_phone(request),
        total_count=total_images,
        nlpsearch=session.get("NLP_MATCH", False),
        exactmatch=session.get("EXACTMATCH", False),
        darkmode=session.get("DarkMode", True),
    )


@app.route("/galleries/<gallery_name>/")
@login_required
def get_galleries(page, per_page) -> list[str]:
    offset = (page - 1) * per_page
    # Use ALL_GALLERIES to get the gallery names
    return ALL_GALLERIES[offset : offset + per_page]


@app.route("/gallery_cover/<gallery_name>/")
@login_required
def get_gallery_cover(gallery_name):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    query = "SELECT i.hash FROM image i JOIN gallery_image gi on i.id = gi.image_id JOIN gallery g on gi.gallery_id = g.id WHERE g.name = %s LIMIT 1"
    cursor.execute(query, (gallery_name,))
    result = cursor.fetchone()
    conn.close()
    filehash = result[0]
    # filepath = get_image_path_by_hash(filehash)
    # if not os.path.exists(filepath):
    #     return send_file("static/imgs/sample1.jpg")
    # img_io, mimetype = ImageResizer(filepath, 1000, 1000)
    filepath = get_cache_image_path(filehash, 1000, 1000)
    if not os.path.exists(filepath):
        return send_file("static/imgs/sample1.jpg")

    # 添加缓存头
    response = make_response(send_file(filepath, mimetype="image/webp"))
    response.cache_control.max_age = 3600  # 缓存 1 小时
    return response
    # return send_file(img_io, mimetype=mimetype)


# 登录页面路由
@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    session["PHONEUA"] = is_phone(request)
    focuspassword = False
    if request.args.get("loginreq") == "True":
        flash("请先登录", "danger")
        print("请先登录")
    if form.validate_on_submit():
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT uid, username, password_hash FROM user WHERE username = %s",
            (form.username.data,),
        )
        user = cursor.fetchone()

        if user and bcrypt.check_password_hash(user[2], form.password.data):
            user_obj = User(id=user[0], username=user[1], password_hash=user[2])
            uname = user[1]
            login_user(user_obj)
            # flash("Login successful!", "success")
            print(f"用户 {uname} 登录成功")
            return redirect(url_for("index"))

        flash("用户名或密码错误", "danger")
        focuspassword = True
    else:
        form.username.data = ""

    return render_template(
        "login.html",
        form=form,
        focuspassword=focuspassword,
        darkmode=session.get("DarkMode", True),
    )


# 管理页面路由 (添加用户)
@app.route("/admin", methods=["GET"])
@login_required
def admin():
    return render_template(
        "admin.html",
        Username=current_user.username,
        users=fetch_users(),
        darkmode=session.get("DarkMode", True),
        nlpsearch=session.get("NLP_MATCH", False),
        exactmatch=session.get("EXACTMATCH", False),
        images=fetch_user_liked(current_user.id),
    )


@app.route("/register", methods=["POST"])
@login_required
def add_user():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    print(f"用户请求注册, 用户名: {username}, 密码: {password}")
    if not username or not password:
        return jsonify({"success": False, "message": "用户名或密码不能为空"})
    else:
        if add_user_to_db(username, password):
            return jsonify(
                {
                    "success": True,
                    "message": f"已添加用户{username}",
                    "user": fetch_user(username),
                }
            )
        else:
            flash(f"用户名 {username} 已存在", "danger")
            return jsonify({"success": False, "message": "用户名已存在"})


@app.route("/delete_user", methods=["POST"])
@login_required
def delete_user_route():
    if request.is_json:
        data = request.get_json()
        user_id = data.get("user_id")
        if not user_id:
            return jsonify({"success": False, "message": "用户ID不能为空"})
        if remove_user_from_db(user_id):
            return jsonify({"success": True, "message": "用户已删除"})
        else:
            return jsonify({"success": False, "message": "用户不存在"})
    else:
        flash("非法请求", "danger")
        return redirect(url_for("admin"))


# 登出路由
@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("_flashes", None)
    return redirect(url_for("login"))


@app.route("/add_tag", methods=["POST"])
def add_tag():
    data = request.get_json()
    image_id = data.get("image_id")
    tag = data.get("tag")
    return add_tag_to_image(image_id, tag)


@app.route("/remove_tag", methods=["POST"])
def remove_tag():
    data = request.get_json()
    image_id = data.get("image_id")
    tag = data.get("tag")
    return remove_tag_from_image(image_id, tag)


@app.route("/toggle_like", methods=["POST"])
def toggle_like():
    data = request.get_json()
    image_id = data.get("image_id")
    return toggle_like_image(image_id, current_user.id)


@app.route("/toggle_darkmode", methods=["POST"])
def toggle_darkmode():
    session["DarkMode"] = not session.get("DarkMode", False)
    return jsonify({"darkmode": session["DarkMode"]})


@app.route("/view_all_liked_images", methods=["GET"])
def view_all_liked_images():
    pass


def add_user_to_db(username:str, password:str):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    # 检查用户名是否已存在
    cursor.execute("SELECT * FROM user WHERE username = %s", (username,))
    if cursor.fetchone():
        conn.close()
        return False
    cursor.execute(
        "INSERT INTO user (username, password_hash) VALUES (%s, %s)",
        (username, bcrypt.generate_password_hash(password).decode("utf-8")),
    )
    conn.commit()
    conn.close()
    return True


# 404页面
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html", darkmode=session.get("DarkMode", True)), 404


if __name__ == "__main__":
    
    #    test_img_insert(
    #      Image.open("./sample1.jpg")
    # )  # 测试插入一张图片 
    # add_user_to_db("admin","passwd")
    # Talisman(app, force_https=True)
    WSGIRequestHandler.protocol_version = "HTTP/1.1"
    app.run(host="0.0.0.0", port=12000, debug=True, threaded=True)
