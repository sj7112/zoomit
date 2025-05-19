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

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)" # bin directory
source "$BIN_DIR/init_main.sh"                                   # main script

# 改cdrom为标准包管理器
init_sources_list() {
  local sources_file="/etc/apt/sources.list"
  if grep -q "^deb cdrom:" "$sources_file"; then
    info "$1" "$DISTRO_OSTYPE"
    file_backup_sj "$sources_file"
    cat >/tmp/sources.list <<EOF
deb http://deb.debian.org/debian $DISTRO_CODENAME main contrib non-free non-free-firmware
deb http://deb.debian.org/debian $DISTRO_CODENAME-updates main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security $DISTRO_CODENAME-security main contrib non-free non-free-firmware
EOF
    $SUDO_CMD mv /tmp/sources.list "$sources_file"
    $SUDO_CMD chmod 644 "$sources_file"
  fi
}

# ==============================================================================
# calc_fast_mirrors - 包管理器镜像测速
# 适用：debian
# 参数：
#   $1 - 存镜像URL的临时文件
# 返回值：
#   通过标准输出返回延迟最低的10个HTTP镜像URL，每行一个
# ==============================================================================
calc_fast_mirrors() {
  info "正在测试最快 {0} 镜像..." $DISTRO_OSTYPE
  $SUDO_CMD apt-get install -y netselect-apt >/dev/null 2>&1
  $SUDO_CMD netselect-apt -t 10 "$DISTRO_CODENAME" 2>/dev/null | grep -Eo 'http://[^ ]+' >"$1"
}

pick_sources_list() {
  local MAIN_SOURCE=".debian.org/debian"
  local NEW_SOURCE="deb $1 $DISTRO_CODENAME main contrib non-free non-free-firmware"
  local APT_SOURCE_LIST="/etc/apt/sources.list"
  # 检查第一行是否匹配主仓库
  if head -n 1 "$APT_SOURCE_LIST" | grep -q "$MAIN_SOURCE"; then
    $SUDO_CMD sed -i "1i $NEW_SOURCE" "$APT_SOURCE_LIST"
  else
    # 不匹配：直接覆盖第一行
    $SUDO_CMD sed -i "1s|^.*|$NEW_SOURCE|" "$APT_SOURCE_LIST"
  fi
}

# --------------------------
# 主执行流程
# --------------------------
init_main "$@"
