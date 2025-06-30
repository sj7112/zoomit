#!/bin/bash
#
# zoomit v1.0 - Copyright (C) 2025 sj7112
# Licensed under the GNU General Public License v3.0
# This is free software: you can redistribute it and/or modify
# it under the terms of the GNU GPL as published by the Free Software Foundation.
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See <https://www.gnu.org/licenses/> for details.
# Project homepage: https://github.com/sj7112/zoomit

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

  # Global variables
  DISTRO_PM=""       # Package manager
  DISTRO_OSTYPE=""   # Distribution name
  DISTRO_CODENAME="" # Distribution codename | version number
  SUDO_CMD=""        # Default sudo command string

  LOG_FILE="/var/log/sj_install.log"
  ERR_FILE="/var/log/sj_pkg_err.log"

  # ==============================================================================
  # Compatibility: debian | ubuntu | centos | rhel | openSUSE | arch Linux
  # Feature 1: check root authority and upgrade the system
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

      # For some distributions, if VERSION_CODENAME is not available
      if [ -z "$DISTRO_CODENAME" ]; then
        # Use version number as a substitute for distributions like Rocky Linux, AlmaLinux, etc.
        DISTRO_CODENAME=$(grep "^VERSION_ID=" /etc/os-release | cut -d= -f2 | tr -d '"' || true)
        case "$DISTRO_OSTYPE" in
          centos)
            # Special handling for CentOS 6/7
            if [[ "$DISTRO_CODENAME" = "6" || "$DISTRO_CODENAME" = "7" ]]; then
              DISTRO_CODENAME=$(sed 's/.*release \([0-9.]*\) .*/\1/' /etc/centos-release)
            fi
            ;;
          arch) DISTRO_CODENAME="arch" ;; # Arch has no codename

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
    # 4. Load JSON environment variables
    # META_Command=$(json_load_data "cmd_meta") # Parse command JSON
  }

  # ==============================================================================
  # Feature 2: Configure SSH (applicable to all distributions)
  # Function: config_sshd
  # Purpose: Check and install sshd, interactively modify SSH port and root login permissions
  # Parameters: None
  # Return Value: None (directly modifies /etc/ssh/sshd_config and restarts sshd)
  # ==============================================================================
  config_sshd() {
    echo ""

    local ssh_service=$([[ $DISTRO_OSTYPE == ubuntu ]] && echo ssh || echo sshd)

    # Check if sshd is installed
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

    # Restart SSH service
    $SUDO_CMD systemctl restart "$ssh_service"
    if [[ $? -eq 0 ]]; then
      info "SSH 配置已生效"
    else
      warning "systemctl restart $ssh_service 失败，请手动执行"
    fi
  }

  # --------------------------
  # Feature 3: Configure static IP
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
  # Feature 4: Install docker composer
  # --------------------------
  docker_compose() {
    install_docker
    infra_setup
    apps_setup
  }

  # --------------------------
  # Feature 5: Close resources
  # --------------------------
  close_all() {
    sh_clear_cache
    echo "=== $INIT_SYSTEM_END - $PRETTY_NAME ==="
  }

  # ==============================================================================
  # Main Function (Compatibility: debian | ubuntu | centos | rhel | openSUSE | arch Linux)
  # ==============================================================================
  init_main() {
    initial_global # Set environment variables
    initial_env    # Initialize basic values
    config_sshd    # Configure SSH
    configure_ip   # Configure static IP
    # docker_compose # Install Docker software
    close_all # close python cache
  }

  show_version() {
    local version="zoomit v1.0"
    local year="2005"
    local author="sj7112"
    echo ""
    string -i "$VERSION_CLAIM" "$version" "$year" "$author"
    echo ""
  }

  if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Check for --version or -v argument
    for arg in "$@"; do
      case "$arg" in
        --version | -v)
          load_global_prop # Load global properties (Step 1)
          show_version
          exit 0
          ;;
      esac
    done

    init_main "$@" # Execute as root
  fi

fi
