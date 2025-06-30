#!/bin/bash

set -e

NEW_PASSWORD="root123"  # 你想设置的新密码

echo "== Step 1: 创建 socket 目录 =="
sudo mkdir -p /var/run/mysqld
sudo chown mysql:mysql /var/run/mysqld

echo "== Step 2: 停止 MySQL 并进入安全模式（跳过权限检查） =="
sudo pkill mysqld || true
sleep 1
sudo mysqld_safe --skip-grant-tables --skip-networking &

echo "等待 MySQL 安全模式启动..."
sleep 8  # 等待 MySQL 启动完成

echo "== Step 3: 重置 root 密码 =="
mysql -u root <<EOF
FLUSH PRIVILEGES;
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '${NEW_PASSWORD}';
EOF

echo "== Step 4: 停止跳过权限的 MySQL 进程 =="
sudo pkill mysqld
sleep 2

echo "== Step 5: 重启 MySQL 服务 =="
sudo systemctl start mysql

echo "✅ 密码已重置为：${NEW_PASSWORD}"
echo "你可以通过 mysql -u root -p 登录。"
