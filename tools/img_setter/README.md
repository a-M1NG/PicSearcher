先使用tagger.sh脚本生成标签txt文件
然后运行命令：
```bash
# 替换"PATH"为实际路径
# 该命令会在每个txt文件所在目录下创建一个tags目录，并将txt文件移动到tags目录中
sudo find "PATH" -type f -name "*.txt" -exec bash -c '
    dir=$(dirname "{}")
    mkdir -p "$dir/tags"
    mv "{}" "$dir/tags/"
' \;
```
然后使用python脚本picture_tags_setter.py将标签图片添加到数据库
注意更改配置脚本中的数据库连接配置信息