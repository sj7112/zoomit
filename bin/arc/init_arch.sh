#!/bin/bash
#
# 一键配置Linux（One-click Configure debian_12）
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

set -euo pipefail # Exit on error, undefined vars, and failed pipes

# 引入消息处理脚本
BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)" # bin directory
source "$BIN_DIR/init_main.sh"                                   # main script

# --------------------------
# 主执行流程
# --------------------------
init_main "$@"
