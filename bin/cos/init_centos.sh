#!/bin/bash
#
# 一键配置Linux（One-click Configure CentOS）
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

# CentOS (yum)
init_sources_list() {
  if grep -q "enabled=1" /etc/yum.repos.d/CentOS-Media.repo 2>/dev/null; then
    info "$1" $DISTRO_OSTYPE

    # 备份所有repo文件
    file_backup_sj "/etc/yum.repos.d/*.repo"

    # 禁用CDROM源
    $SUDO_CMD sed -i 's/enabled=1/enabled=0/' /etc/yum.repos.d/CentOS-Media.repo

    ARCH_URL=$([ "$(uname -m)" == "x86_64" ] && echo "x86_64" || echo "i386")

    # 创建新的Base.repo文件（这里用的是标准镜像）
    cat >/tmp/CentOS-Base.repo <<EOF
[base]
name=CentOS-$DISTRO_CODENAME - Base - mirror.centos.org
baseurl=https://mirror.centos.org/centos/$DISTRO_CODENAME/os/\$ARCH_URL/
gpgcheck=1
gpgkey=https://mirror.centos.org/centos/RPM-GPG-KEY-CentOS-$DISTRO_CODENAME

[updates]
name=CentOS-$DISTRO_CODENAME - Updates - mirror.centos.org
baseurl=https://mirror.centos.org/centos/$DISTRO_CODENAME/updates/\$ARCH_URL/
gpgcheck=1
gpgkey=https://mirror.centos.org/centos/RPM-GPG-KEY-CentOS-$DISTRO_CODENAME

[extras]
name=CentOS-$DISTRO_CODENAME - Extras - mirror.centos.org
baseurl=https://mirror.centos.org/centos/$DISTRO_CODENAME/extras/\$ARCH_URL/
gpgcheck=1
gpgkey=https://mirror.centos.org/centos/RPM-GPG-KEY-CentOS-$DISTRO_CODENAME
EOF
    $SUDO_CMD mv /tmp/CentOS-Base.repo /etc/yum.repos.d/CentOS-Base.repo

    # 清除缓存并重建
    $SUDO_CMD yum clean all
    $SUDO_CMD yum makecache
  fi
}

calc_fast_mirrors() {
  yum install -y yum-utils
  curl -s http://mirrorlist.centos.org/?release=$(rpm -E %r) &
  arch=$(uname -m) \
    | head -10 >/tmp/mirrors.txt

  apt-get install -y netselect-apt
  netselect-apt -n 10 -t 60 $(lsb_release -cs) | tee /tmp/mirrors.txt
}

pick_sources_list() {
  echo "deb http://$selected/debian $DISTRO_CODENAME main" >/etc/apt/sources.list
}

# --------------------------
# 主执行流程
# --------------------------
echo "=== sj init debian system start ==="
# check_env
# check_dvd
# update_sys
config_sshd
# configure_ip
# install_software
# system_config
echo "=== sj init debian system end ==="
