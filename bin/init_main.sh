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

  LOG_FILE="/var/log/sj_install.log"
  ERR_FILE="/var/log/sj_pkg_err.log"

  # ==============================================================================
  # 兼容：debian | ubuntu | centos | rhel | openSUSE | arch Linux
  # 功能1: 检查root权限并自动升级
  # ==============================================================================
  # initial sudo param
  check_user_auth() {
    if [ "$(id -u)" -ne 0 ]; then
      if ! command -v sudo &>/dev/null; then
        exiterr -i "INIT_SUDO_NO_EXIST"
      fi
      SUDO_CMD="sudo" # If not root, elevate privileges
    fi

    # Set log file owner to the current user and current group, with 644 permissions
    [[ -f "$LOG_FILE" ]] || $SUDO_CMD touch "$LOG_FILE"
    [[ -f "$ERR_FILE" ]] || $SUDO_CMD touch "$ERR_FILE"
    $SUDO_CMD chown "$USER:$USER" "$LOG_FILE" "$ERR_FILE"
    $SUDO_CMD chmod 644 "$LOG_FILE" "$ERR_FILE"
  }

  # ** Environment parameters: package management | os name **
  init_os_release() {
    if [ -f /etc/os-release ]; then
      . /etc/os-release
      DISTRO_OSTYPE="$ID"
      case "$ID" in
        debian | ubuntu) DISTRO_PM="apt" ;; # Debian | Ubuntu
        centos) DISTRO_PM="yum" ;;          # CentOS
        rhel) DISTRO_PM="dnf" ;;            # RHEL
        arch) DISTRO_PM="pacman" ;;         # Arch
        opensuse* | suse)
          DISTRO_OSTYPE="opensuse"
          DISTRO_PM="zypper" # openSUSE
          ;;
        *) exiterr -i "$INIT_LINUX_UNSUPPORT: $ID ($PRETTY_NAME)" ;;
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
          arch) DISTRO_CODENAME="arch" ;; # Arch无代号

        esac
      fi
    elif command -v lsb_release &>/dev/null; then
      DISTRO_CODENAME=$(lsb_release -c | awk '{print $2}' || true)
    else
      DISTRO_CODENAME="unknown"
    fi
  }

  # ==============================================================================
  # Initial environment variables: package manager | operating system name
  # ==============================================================================
  initial_global() {
    load_global_prop # Load global properties (Step 1)
    check_user_auth  # initial sudo param
    init_os_release  # initial distribution data
    echo -e "\n=== $INIT_SYSTEM_START - $PRETTY_NAME ===\n"
    initial_language  # fix shell language to ensure UTF-8 support
    load_global_prop  # Load global properties (Step 2)
    load_message_prop # load message translations
  }

  # ==============================================================================
  # Initial environment: python 3.10 | install packages
  # ==============================================================================
  initial_env() {
    # 1. install Python3 virtual environment
    create_py_venv
    # 2. Select and update package manager
    sh_update_source
    # 3. Install basic packages
    install_base_pkg "sudo"
    install_base_pkg "wget"
    install_base_pkg "curl"
    install_base_pkg "jq"
    install_base_pkg "make"
    # 4. 加载json环境变量
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
    echo ""

    local ssh_service=$([[ $DISTRO_OSTYPE == ubuntu ]] && echo ssh || echo sshd)

    # 检查是否安装 sshd
    if ! ($SUDO_CMD systemctl is-active ssh &>/dev/null || $SUDO_CMD systemctl is-active sshd &>/dev/null); then
      info "sshd 未安装，正在安装..."
      if [[ "$DISTRO_PM" = "zypper" || "$DISTRO_PM" = "pacman" ]]; then
        install_base_pkg "openssh"
      else
        install_base_pkg "openssh-server"
      fi
      $SUDO_CMD systemctl enable --now "$ssh_service"
    fi

    set +e
    sh_config_sshd # python adds-on: config /etc/ssh/sshd_config
    if [[ $? -ne 0 ]]; then
      return
    fi
    set -e

    # 重启 SSH 服务
    $SUDO_CMD systemctl restart "$ssh_service"
    if [[ $? -eq 0 ]]; then
      info "SSH 配置已生效"
    else
      warning "systemctl restart $ssh_service 失败，请手动执行"
    fi
  }

  # --------------------------
  # 功能3: 配置静态IP
  # --------------------------
  configure_ip() {
    echo ""

    set +e
    sh_fix_ip # python adds-on: config network as fix ip
    if [[ $? -ne 0 ]]; then
      return
    else
      init_env_nw
    fi
    set -e

    network_config
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

  # --------------------------
  # 功能3: 安装指定软件
  # --------------------------
  close_all() {
    sh_clear_cache
    echo "=== $INIT_SYSTEM_END - $PRETTY_NAME ==="
  }

  # ==============================================================================
  # 公共初始化子函数（兼容：debian | ubuntu | centos | rhel | openSUSE | arch Linux）
  # ==============================================================================
  init_main() {
    initial_global # 设置环境变量
    initial_env    # 基础值初始化
    config_sshd    # SSH配置
    configure_ip   # 静态IP配置
    # docker_compose # 安装软件
    close_all # close python cache
  }

  if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    init_main "$@" # Execute as root
  fi

fi
