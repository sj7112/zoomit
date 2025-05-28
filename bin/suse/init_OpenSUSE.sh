#!/bin/bash
#
# 一键配置Linux（One-click Configure OpenSUSE）
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

# OpenSUSE (zypper)
init_sources_list() {
  # 检查是否包含 cdrom 源
  if grep -q "cdrom" /etc/zypp/repos.d/*.repo; then
    info "$1" $DISTRO_OSTYPE

    # 备份原来的 repo 文件
    file_backup_sj "/etc/zypp/repos.d/*.repo"

    # 修改 repo 配置文件，将 cdrom 源替换为官方源
    for repo_file in /etc/zypp/repos.d/*.repo; do
      if grep -q "cdrom" "$repo_file"; then
        # 替换为默认的官方 OpenSUSE 源
        cat >"$repo_file" <<EOF
[openSUSE-oss]
name=Main Repository
enabled=1
autorefresh=1
baseurl=http://download.opensuse.org/distribution/leap/$DISTRO_CODENAME/repo/oss/
path=/
type=rpm-md

[openSUSE-non-oss]
name=Non-OSS Repository
enabled=1
autorefresh=1
baseurl=http://download.opensuse.org/distribution/leap/$DISTRO_CODENAME/repo/non-oss/
path=/
type=rpm-md

[openSUSE-update]
name=Update Repository
enabled=1
autorefresh=1
baseurl=http://download.opensuse.org/update/leap/$DISTRO_CODENAME/oss/
path=/
type=rpm-md
EOF
      fi
    done
  fi
}

# --------------------------
# 主执行流程
# --------------------------
echo "=== sj init debian system start ==="
# initial_env
config_sshd
# configure_ip
# install_software
# system_config
echo "=== sj init debian system end ==="
