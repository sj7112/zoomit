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

set -euo pipefail                                                # strict mode
BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)" # bin directory
source "$BIN_DIR/init_main.sh"                                   # main script

# Arch Linux (pacman)
init_sources_list() {
  # 检查是否使用了本地文件源
  if grep -q "^Server = file://" /etc/pacman.d/mirrorlist; then
    info "$1" $DISTRO_OSTYPE

    # 备份原镜像列表
    file_backup_sj "/etc/pacman.d/mirrorlist"

    # 创建新的镜像列表文件，使用官方全球镜像
    cat >/tmp/mirrorlist <<EOF
# Arch Linux 官方全球镜像
# 全球自动重定向
Server = https://geo.mirror.pkgbuild.com/\$repo/os/\$arch

# 主要镜像
Server = https://mirrors.kernel.org/archlinux/\$repo/os/\$arch
Server = https://mirror.rackspace.com/archlinux/\$repo/os/\$arch
Server = https://mirror.leaseweb.net/archlinux/\$repo/os/\$arch
Server = https://arch.mirror.constant.com/\$repo/os/\$arch

# 官方主源
Server = https://archlinux.org/\$repo/os/\$arch
EOF
    $SUDO_CMD mv /tmp/mirrorlist /etc/pacman.d/mirrorlist

    # 更新软件包数据库
    $SUDO_CMD pacman -Syy
  fi
}

# --------------------------
# 主执行流程
# --------------------------
echo "=== sj init debian system start ==="
# initial_env
# check_dvd
config_sshd
# configure_ip
# install_software
# system_config
echo "=== sj init debian system end ==="
