#!/bin/bash

# Load once only
if [[ -z "${LOADED_INIT_MAIN:-}" ]]; then
  LOADED_INIT_MAIN=1

  set -euo pipefail # Exit on error, undefined vars, and failed pipes

  : "${BIN_DIR:="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"}" # bin directory
  : "${LIB_DIR:="$(dirname "$BIN_DIR")/lib"}"                     # lib direcotry
  source "$LIB_DIR/msg_handler.sh"
  source "$LIB_DIR/lang_utils.sh"
  source "$LIB_DIR/bash_utils.sh"
  source "$LIB_DIR/cmd_handler.sh"
  source "$LIB_DIR/json_handler.sh"
  source "$LIB_DIR/system.sh"
  source "$LIB_DIR/hash_util.sh"
  source "$LIB_DIR/python_install.sh"
  source "$LIB_DIR/python_bridge.sh"
  source "$LIB_DIR/update_env.sh"
  source "$LIB_DIR/network.sh"
  source "$LIB_DIR/docker.sh"

  # 全局变量
  DISTRO_PM=""       # 包管理器
  DISTRO_OSTYPE=""   # 发行版名称
  DISTRO_CODENAME="" # 发行版代号 | 版本号
  SUDO_CMD=""        # sudo 默认字符串

  # ** 环境变量：包管理器 | 操作系统名称 **
  initial_global() {
    if [ -f /etc/os-release ]; then
      . /etc/os-release
      DISTRO_OSTYPE="$ID"
      case "$ID" in
        debian | ubuntu)
          DISTRO_PM="apt" # Debian | Ubuntu
          ;;
        centos)
          DISTRO_PM="yum" # CentOS
          ;;
        rhel)
          DISTRO_PM="dnf" # RHEL
          ;;
        opensuse* | suse)
          DISTRO_OSTYPE="opensuse"
          DISTRO_PM="zypper" # openSUSE
          ;;
        arch)
          DISTRO_PM="pacman" # Arch
          ;;
        *)
          exiterr -i "$INIT_LINUX_UNSUPPORT: $ID ($PRETTY_NAME)"
          ;;
      esac
    else
      exiterr -i "$INIT_LINUX_UNSUPPORT"
    fi

    # ** Env param：Distribution codename | version codename **
    if [ -f /etc/os-release ]; then
      DISTRO_CODENAME=$(grep "^VERSION_CODENAME=" /etc/os-release | cut -d'=' -f2 || true)

      # 部分发行版如没有VERSION_CODENAME
      if [ -z "$DISTRO_CODENAME" ]; then
        # Rocky Linux、AlmaLinux 等用版本号替代
        DISTRO_CODENAME=$(grep "^VERSION_ID=" /etc/os-release | cut -d= -f2 | tr -d '"' || true)
        case "$DISTRO_OSTYPE" in
          centos)
            # CentOS 6/7 特判
            if [[ "$DISTRO_CODENAME" = "6" || "$DISTRO_CODENAME" = "7" ]]; then
              DISTRO_CODENAME=$(sed 's/.*release \([0-9.]*\) .*/\1/' /etc/centos-release)
            fi
            ;;
          arch)
            # Arch无代号
            DISTRO_CODENAME="arch"
            ;;
        esac
      fi
    elif command -v lsb_release &>/dev/null; then
      DISTRO_CODENAME=$(lsb_release -c | awk '{print $2}' || true)
    else
      DISTRO_CODENAME="unknown"
    fi
  }

  # Initial language & translations
  initial_language() {
    fix_shell_locale  # fix shell language to ensure UTF-8 support
    load_global_prop  # Load global properties (Step 2)
    load_message_prop # load message translations
  }

  # ==============================================================================
  # 函数: initial_env 检查root权限和sudo
  # @i18n: This function needs internationalization
  # ==============================================================================
  initial_env() {
    # 2. 检查并安装 Python3 虚拟环境
    install_py_venv
    # 3. 选择包管理器，并执行初始化
    sh_update_source
    # 4. 安装各类基础包
    info "安装所需软件包..."
    install_base_pkg "sudo"
    install_base_pkg "wget"
    install_base_pkg "curl"
    install_base_pkg "jq"
    install_base_pkg "make"
    # 5. 加载json环境变量；初始化语言和国家代码变量
    # META_Command=$(json_load_data "cmd_meta") # 命令解析json

  }

  # ==============================================================================
  # 功能2: 配置SSH（适用于所有发行版本）
  # 函数: config_sshd
  # 作用: 检查并安装 sshd，交互式修改 SSH 端口和 root 登录权限
  # 参数: 无
  # 返回值: 无 (直接修改 /etc/ssh/sshd_config 并重启 sshd)
  # ==============================================================================
  config_sshd() {
    local sshd_config="/etc/ssh/sshd_config"
    echo ""

    # 检查是否安装 sshd
    if ! ($SUDO_CMD systemctl is-active ssh &>/dev/null || $SUDO_CMD systemctl is-active sshd &>/dev/null); then
      info "sshd 未安装，正在安装..."
      if [[ "$DISTRO_PM" = "zypper" || "$DISTRO_PM" = "pacman" ]]; then
        install_base_pkg "openssh"
      else
        install_base_pkg "openssh-server"
      fi
      if [[ "$DISTRO_OSTYPE" = "ubuntu" ]]; then
        $SUDO_CMD systemctl enable --now ssh
      else
        $SUDO_CMD systemctl enable --now sshd
      fi
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
    #PermitRootLogin prohibit-password
    read -rp "允许 root 远程登录？[y/N]: " allow_root
    case "$allow_root" in
      [Yy]) fl_modify_line "$sshd_config" "PermitRootLogin" "PermitRootLogin yes" && info "已允许 root 登录" ;;
      [Nn] | "") fl_modify_line "$sshd_config" "PermitRootLogin" "PermitRootLogin no" && info "已禁止 root 登录" ;;
    esac

    # 重启 SSH 服务
    if [[ "$DISTRO_OSTYPE" = "ubuntu" ]]; then
      $SUDO_CMD systemctl restart ssh
    else
      $SUDO_CMD systemctl restart sshd
    fi
    if [[ $? -eq 0 ]]; then
      info "SSH 配置已应用"
    fi
  }

  # --------------------------
  # 功能3: 配置静态IP
  # --------------------------
  configure_ip() {
    set +e
    sh_fix_ip # 设置环境配置文件
    if [[ $? -ne 0 ]]; then
      return
    else
      init_env_nw "$ENV_NW_PATH"
    fi
    set -e

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

  install_docker() {
    info "在 $DISTRO 上安装 Docker 与 Docker Compose..."

    # 安装依赖
    install_base_pkg "ca-certificates"
    install_base_pkg "gnupg"

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
  # 功能2: 安装指定软件
  # --------------------------
  docker_compose() {
    install_docker
    infra_setup
    apps_setup
  }

  # ==============================================================================
  # 公共初始化子函数（兼容：debian | ubuntu | centos | rhel | openSUSE | arch Linux）
  # ==============================================================================
  init_main() {
    initial_global # 设置环境变量
    echo -e "\n=== $INIT_SYSTEM_START - $PRETTY_NAME ===\n"
    initial_language # inital language & translation
    initial_env      # 基础值初始化
    config_sshd      # SSH配置
    configure_ip     # 静态IP配置
    # docker_compose # 安装软件
    echo "=== $INIT_SYSTEM_END - $PRETTY_NAME ==="
  }

  if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    load_global_prop # Load global properties (Step 1)
    if [[ $EUID -ne 0 ]]; then
      if ! command -v sudo &>/dev/null; then
        exiterr -i "$INIT_SUDO_NO_EXIST"
      fi
      exec sudo "$0" "$@" # If not root, elevate privileges
    fi
    echo "$(id)"
    init_main "$@" # Execute as root
  fi

fi
