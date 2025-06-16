#!/bin/bash
#
# 一键配置Linux（One-click Configure debian）
# 自动操作：
#   1）换默认语言、自动升级安装包
#   3）安装ssh
#   4）安装网络、配置DNS
#   5）安装docker-ce
# docker选装：
#   1）redis
#   2）postgres
#   3）mariadb
#   4）minio
#   5）nginx
# 使用示例:
# sudo ./init_main.sh

# 检查 DEBUG 环境变量，设置相应的调试模式

if [[ "$DEBUG" == "1" ]]; then
  # set -x          # 启用命令追踪
  set -e          # 启用脚本错误即退出
  set -u          # 启用未定义变量报错
  set -o pipefail # 启用管道失败时退出
else
  set +x          # 关闭命令追踪
  set -e          # 确保遇到错误退出
  set -u          # 确保未定义变量时报错
  set -o pipefail # 确保管道中的命令失败会导致脚本退出
fi

# 引入消息处理脚本
BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)" # bin directory
source "$BIN_DIR/init_main.sh"                                   # main script

install_docker() {
  info "在 $DISTRO 上安装 Docker 与 Docker Compose..."

  # 更新包索引并安装依赖
  apt-get update
  apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    apt-transport-https

  # 添加 Docker 仓库 GPG（可选，但推荐）
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/$DISTRO/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  # 添加 Docker 仓库源
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$DISTRO \
      $(lsb_release -cs) stable" >/etc/apt/sources.list.d/docker.list

  # 安装 Docker
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  # 验证安装
  docker --version
  docker compose version
}
# --------------------------
# 主执行流程
# --------------------------
init_main "$@"
