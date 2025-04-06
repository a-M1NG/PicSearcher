#!/bin/bash
# 加载配置
source tools/img_setter/config.sh


echo "=== 开始标签生成 ==="
./tools/img_setter/tagger.sh

echo "=== 整理标签文件 ==="
find "$WORK_ROOT" -type f -name "*.txt" -exec bash -c '
    dir=$(dirname "{}")
    mkdir -p "$dir/tags"
    mv "{}" "$dir/tags/"
' \;

echo "=== 导入数据库 ==="
/home/ming/miniconda3/envs/webdev/bin/python tools/img_setter/picture_tags_setter.py

echo "=== 工作流完成 ==="