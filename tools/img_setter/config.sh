#!/bin/bash
# 统一配置文件 - 只需在这里修改路径

# 主工作目录（所有相对路径都基于此）
export WORK_ROOT="/home/ming/Pictures/pixabay_images"

export TAGGER_INPUT_DIR="$WORK_ROOT"  # 图片输入路径

# 数据库导入配置
export DB_IMPORT_PATHS="$WORK_ROOT"  # 可以设置多个路径，用冒号分隔