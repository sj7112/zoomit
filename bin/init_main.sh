#!/bin/bash

# 确保只被加载一次
if [[ -z "${LOADED_INIT_MAIN:-}" ]]; then
  LOADED_INIT_MAIN=1

  LIB_DIR="$(dirname "$BIN_DIR")/lib" # lib direcotry
  source "$LIB_DIR/msg_handler.sh"
  source "$LIB_DIR/bash_utils.sh"
  source "$LIB_DIR/cmd_handler.sh"
  source "$LIB_DIR/json_handler.sh"
  source "$LIB_DIR/system.sh"
  source "$LIB_DIR/hash_util.sh"
  source "$LIB_DIR/init_base_func.sh"
  source "$LIB_DIR/python_bridge.sh"
  source "$LIB_DIR/update_env.sh"
  source "$LIB_DIR/network.sh"

  # 全局变量
  DISTRO_PM=""       # 包管理器
  DISTRO_OSTYPE=""   # 发行版名称
  DISTRO_CODENAME="" # 发行版代号 | 版本号
  SYSTEM_LANG=""     # 语言代码（默认=en）
  SYSTEM_COUNTRY=""  # 国家代码（默认=CN）
  SUDO_CMD=""        # sudo 默认为空字符串

  # ==============================================================================
  # 兼容：debian | ubuntu | centos | RHEL | openSUSE | arch Linux
  # 功能1: 检查root权限并自动升级
  # ==============================================================================

  # ==============================================================================
  # 函数: initial_env 检查root权限和sudo
  # @i18n: This function needs internationalization
  # ==============================================================================
  initial_env() {
    # 1. 检查用户权限，自动安装sudo
    info "[1] 检查系统环境..."
    if [ "$(id -u)" -eq 0 ]; then
      install_base_pkg "sudo" # 此时 SUDO_CMD=""
    else
      if ! command -v sudo &>/dev/null; then
        exiterr "无法以非 root 安装 sudo，请联系管理员或使用 root 账号"
      elif sudo -v; then # 如有需要，会提示用户输入密码
        SUDO_CMD="sudo"
        success "sudo 权限验证成功，后续命令自动使用 sudo"
      else
        exiterr "当前用户没有足够的 sudo 权限，无法继续执行"
      fi
    fi

    # 2. 调整 root 语言设置
    source_defualt_lang

    # 3. 初始化语言和国家代码变量
    SYSTEM_LANG=$(get_locale_code)
    SYSTEM_COUNTRY=$(get_country_code | tr '[:lower:]' '[:upper:]')

    # 4. 安装各类基础包
    install_base_pkg "curl"
    install_base_pkg "jq"
  }

  # ==============================================================================
  # 函数: check_dvd 检查apt软件源并自动替换
  # ==============================================================================
  check_dvd() {
    # 检查是否包含 cdrom 源
    init_sources_list "检测到 CD-ROM 作为软件源，修改为默认 {0} 官方源..."
    # 选择速度快的镜像
    select_mirror # 内有交互

    info "==== 系统升级开始 ===="
    clean_pkg_mgr   # 清理缓存
    update_pkg_mgr  # 更新镜像源列表
    upgrade_pkg_mgr # 升级已安装的软件包
    remove_pkg_mgr  # 删除不再需要的依赖包
    success "==== 系统升级完成 ===="
  }

  # ==============================================================================
  # 函数: update_sys 换语言 & 自动升级
  # ==============================================================================
  # update_sys() {
  #   info "==== 系统升级开始 ===="

  #   # 2. 系统更新
  #   info "[2/3] 升级系统软件..."
  #   $SUDO_CMD apt-get update
  #   DEBIAN_FRONTEND=noninteractive $SUDO_CMD apt-get upgrade -y
  #   DEBIAN_FRONTEND=noninteractive $SUDO_CMD apt-get full-upgrade -y

  #   # 3. 清理
  #   info "[3/3] 清理无用包..."
  #   $SUDO_CMD apt-get autoremove -y
  #   $SUDO_CMD apt-get clean

  #   success "系统升级完成"
  # }

  # ==============================================================================
  # 功能2: 配置SSH（适用于所有发行版本）
  # 函数: config_sshd
  # 作用: 检查并安装 sshd，交互式修改 SSH 端口和 root 登录权限
  # 参数: 无
  # 返回值: 无 (直接修改 /etc/ssh/sshd_config 并重启 sshd)
  # ==============================================================================
  config_sshd() {
    local sshd_config="/etc/ssh/sshd_config"

    # 检查是否安装 sshd
    if ! command -v sshd &>/dev/null; then
      info "sshd 未安装，正在安装..."
      $SUDO_CMD apt-get update && $SUDO_CMD apt-get install -y openssh-server || exiterr "安装 sshd 失败"
    fi

    # 询问 SSH 端口
    curr_ssh_port=$(grep -oP '^Port \K\d+' "$sshd_config" || echo 22)
    read -p "$(string "输入新的SSH端口 (当前: {0}) : " $curr_ssh_port)" ssh_port
    if [[ "$ssh_port" =~ ^[0-9]+$ && "$ssh_port" -le 65535 ]]; then
      $SUDO_CMD sed -i "s/^#*Port .*/Port $ssh_port/" "$sshd_config"
      info "已设置SSH端口: {0}" "$ssh_port"
    else
      info "无效端口，保持默认: $curr_ssh_port" >&2
    fi

    # 询问是否允许 root 登录
    read -rp "允许 root 远程登录？[y/N]: " allow_root
    case "$allow_root" in
      [Yy]) fl_modify_line "$sshd_config" "PermitRootLogin" "PermitRootLogin yes" && info "已允许 root 登录" ;;
      [Nn] | "") fl_modify_line "$sshd_config" "PermitRootLogin" "PermitRootLogin no" && info "已禁止 root 登录" ;;
    esac

    # 重启 SSH 服务
    $SUDO_CMD systemctl restart sshd && info "SSH 配置已应用"
  }

  # --------------------------
  # 功能3: 配置静态IP
  # --------------------------
  configure_ip() {
    # 设置环境配置文件
    if ! need_fix_ip; then
      return 0
    fi
    if [[ ${ENV_NETWORK["CURR_NM"]} == "NetworkManager" ]]; then
      info "NetworkManager 正在运行"
      config_nmcli
    elif [[ ${ENV_NETWORK["CURR_NM"]} == "networking" ]]; then
      info "ifupdown 正在运行"
      ifupdown_to_systemd_networkd
    elif [[ ${ENV_NETWORK["CURR_NM"]} == "wicked" ]]; then
      info "wicked 正在运行"
      # wicked_to_systemd_networkd
    elif [[ ${ENV_NETWORK["CURR_NM"]} == "network" ]]; then
      info "network-scripts 正在运行"
      # network_to_systemd_networkd
    elif [[ ${ENV_NETWORK["CURR_NM"]} == "systemd-networkd" ]]; then
      info "systemd-networkd 正在运行"
      config_default
    else
      exiterr "未知网络管理器，无法配置静态IP"
    fi

  }

  # --------------------------
  # 加载环境变量
  # --------------------------
  ENV_FILE="~/sj_auto_install/config/infrastructure/.env"
  CONFIG_DIR=$(dirname "$ENV_FILE")
  # 加载配置
  source "$ENV_FILE"

  # --------------------------
  # 功能2: 安装指定软件
  # --------------------------
  docker_compose() {
    echo "[2/3] 正在安装软件: ${SOFTWARE_LIST}..."

    # 更新包列表
    apt-get update -qq

    # 安装每个指定的软件
    for software in ${SOFTWARE_LIST}; do
      case "${software}" in
        postgres)
          echo "-> 安装PostgreSQL..."
          apt-get install -y postgresql postgresql-contrib
          systemctl enable postgresql
          ;;
        redis)
          echo "-> 安装Redis..."
          apt-get install -y redis-server
          systemctl enable redis-server
          ;;
        nginx)
          echo "-> 安装Nginx..."
          apt-get install -y nginx
          systemctl enable nginx
          ;;
        *)
          echo "警告: 未知软件 '${software}'，跳过安装" >&2
          ;;
      esac
    done
  }

  # CentOS/RHEL (yum/dnf)
  handle_yum() {
    if grep -q "cdrom" /etc/yum.repos.d/*; then
      info "检测到 CD-ROM 作为软件源，正在修改为默认 CentOS/RHEL 官方源..."
      $SUDO_CMD cp /etc/yum.repos.d/* /etc/yum.repos.d/*.bak
      cat >/tmp/centos.repo <<EOF
[base]
name=CentOS-7 - Base
baseurl=http://mirror.centos.org/centos/7/os/x86_64/
enabled=1
gpgcheck=1
gpgkey=http://mirror.centos.org/centos/RPM-GPG-KEY-CentOS-7
EOF
      $SUDO_CMD mv /tmp/centos.repo /etc/yum.repos.d/centos.repo
      success "已更新 repo 文件"
    else
      info "未检测到 CD-ROM 作为软件源，无需修改。"
    fi
  }

  # Arch Linux (pacman)
  handle_pacman() {
    if grep -q "^cdrom" /etc/pacman.conf; then
      info "检测到 CD-ROM 作为软件源，正在修改为默认 Arch 官方源..."
      $SUDO_CMD cp /etc/pacman.conf /etc/pacman.conf.bak
      cat >/tmp/pacman.conf <<EOF
[core]
Server = http://mirror.rackspace.com/archlinux/\$repo/os/\$arch
[extra]
Server = http://mirror.rackspace.com/archlinux/\$repo/os/\$arch
[community]
Server = http://mirror.rackspace.com/archlinux/\$repo/os/\$arch
EOF
      $SUDO_CMD mv /tmp/pacman.conf /etc/pacman.conf
      success "已更新 pacman.conf"
    else
      info "未检测到 CD-ROM 作为软件源，无需修改。"
    fi
  }

  # OpenSUSE (zypper)
  handle_zypper() {
    if grep -q "^cdrom" /etc/zypp/repos.d/*; then
      info "检测到 CD-ROM 作为软件源，正在修改为默认 OpenSUSE 官方源..."
      $SUDO_CMD cp /etc/zypp/repos.d/* /etc/zypp/repos.d/*.bak
      cat >/tmp/suse.repo <<EOF
[openSUSE]
name=openSUSE
baseurl=http://download.opensuse.org/distribution/leap/15.3/repo/oss/
enabled=1
gpgcheck=1
gpgkey=http://download.opensuse.org/repositories/oss/15.3/repodata/repomd.xml.key
EOF
      $SUDO_CMD mv /tmp/suse.repo /etc/zypp/repos.d/openSUSE.repo
      success "已更新 repo 文件"
    else
      info "未检测到 CD-ROM 作为软件源，无需修改。"
    fi
  }

  # ==============================================================================
  # 公共初始化子函数（兼容：debian | ubuntu | centos | RHEL | openSUSE | arch Linux）
  # ==============================================================================
  init_main() {
    # ** 环境变量：包管理器 | 操作系统名称 **
    if command -v apt &>/dev/null; then
      DISTRO_PM="apt" # Debian | Ubuntu
      DISTRO_OSTYPE=$(grep -q "ID=debian" /etc/os-release && echo "Debian" || echo "Ubuntu")
    elif command -v dnf &>/dev/null; then
      DISTRO_PM="dnf" # RHEL
      DISTRO_OSTYPE="RHEL"
    elif command -v yum &>/dev/null; then
      DISTRO_PM="yum" # CentOS
      DISTRO_OSTYPE="CentOS"
    elif command -v pacman &>/dev/null; then
      DISTRO_PM="pacman" # Arch
      DISTRO_OSTYPE="Arch"
    elif command -v zypper &>/dev/null; then
      DISTRO_PM="zypper" # OpenSUSE
      DISTRO_OSTYPE="OpenSUSE"
    else
      exiterr "无法识别包管理器，系统类型不支持，无法继续执行"
    fi

    # ** 环境变量：发行版代号 | 版本号 **
    if command -v lsb_release &>/dev/null; then
      DISTRO_CODENAME=$(lsb_release -c | awk '{print $2}')
    else
      # 如果 lsb_release 不存在，根据其他方法获取发行版代号
      if [ "$(id -u)" = "yum" ]; then
        DISTRO_CODENAME=$(rpm -q --qf '%{VERSION}' centos-release) # Centos 没有代号，返回版本号
      elif [ "$(id -u)" = "pacman" ]; then
        DISTRO_CODENAME="arch" # Arch Linux 没有代号，返回 "arch"
      elif [ -f /etc/os-release ]; then
        DISTRO_CODENAME=$(grep "^VERSION_CODENAME=" /etc/os-release | cut -d'=' -f2)
      else
        DISTRO_CODENAME="unknown"
      fi
    fi

    echo "=== sj init $DISTRO_OSTYPE system start ==="
    initial_env # 基础值初始化
    # check_dvd # 检查软件源
    # config_sshd # SSH配置
    # configure_ip # 静态IP配置
    docker_compose # 安装软件
    # system_config
    echo "=== sj init $DISTRO_OSTYPE system end ==="
  }
fi
