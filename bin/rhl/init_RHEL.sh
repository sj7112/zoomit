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

# RHEL (dnf)
init_sources_list() {
  if grep -q "cdrom" /etc/yum.repos.d/*.repo; then
    info "$1" $DISTRO_OSTYPE

    # 备份所有repo文件
    file_backup_sj "/etc/yum.repos.d/*.repo"

    # 修改 repo 配置文件，将 cdrom 源替换为官方源
    for repo_file in /etc/yum.repos.d/*.repo; do
      if grep -q "cdrom" "$repo_file"; then
        # 替换为默认的官方 RHEL 源，这里以 CentOS 为例，你可以根据需要修改为官方 RHEL 镜像
        cat >"$repo_file" <<EOF
[rhel-base]
name=Red Hat Enterprise Linux \$releasever - \$basearch
baseurl=https://mirror.rhel.org/redhat/rhel/\$releasever/os/\$basearch/
enabled=1
gpgcheck=1
gpgkey=https://mirror.rhel.org/redhat/RPM-GPG-KEY-redhat-release

[rhel-updates]
name=Red Hat Enterprise Linux \$releasever - \$basearch - Updates
baseurl=https://mirror.rhel.org/redhat/rhel/\$releasever/updates/\$basearch/
enabled=1
gpgcheck=1
gpgkey=https://mirror.rhel.org/redhat/RPM-GPG-KEY-redhat-release
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
# check_dvd
config_sshd
# configure_ip
# install_software
# system_config
echo "=== sj init debian system end ==="
