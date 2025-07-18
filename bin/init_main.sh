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

# ==============================================================================
# Compatibility: debian | ubuntu | centos | rhel | openSUSE | arch Linux
# ==============================================================================

# Load once only
if [[ -z "${LOADED_INIT_MAIN:-}" ]]; then
  LOADED_INIT_MAIN=1

  set -euo pipefail # Exit on error, undefined vars, and failed pipes

  : "${BIN_DIR:="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"}" # bin directory
  : "${LIB_DIR:="$(dirname "$BIN_DIR")/lib"}"                     # lib direcotry
  source "$LIB_DIR/msg_handler.sh"
  source "$LIB_DIR/lang_utils.sh"
  source "$LIB_DIR/read_util.sh"
  source "$LIB_DIR/cmd_handler.sh"
  source "$LIB_DIR/json_handler.sh"
  source "$LIB_DIR/system.sh"
  source "$LIB_DIR/hash_util.sh"
  source "$LIB_DIR/python_install.sh"
  source "$LIB_DIR/python_bridge.sh"
  source "$LIB_DIR/update_env.sh"
  source "$LIB_DIR/network.sh"
  source "$LIB_DIR/docker_install.sh"
  source "$LIB_DIR/read_multi_util.sh"

  # Global variables
  DISTRO_PM=""       # Package manager
  DISTRO_OSTYPE=""   # Distribution name
  DISTRO_CODENAME="" # Distribution codename | version number

  PY_INST_DIR="" # Python installation directory
  VENV_DIR=""    # Python virtual environment directory
  VENV_BIN=""    # Python virtual environment executable

  LOG_FILE="/var/log/sj_install.log"
  ERR_FILE="/var/log/sj_pkg_err.log"

  # ==============================================================================
  # Feature 1: check root authority and upgrade the system
  # ==============================================================================
  # initial sudo param
  initial_log_file() {
    # Set log file owner to the current user and current group, with 644 permissions
    user_file_permit "$LOG_FILE" "$ERR_FILE" "--showinfo" "--mode=644"
  }

  # ** Environment parameters: package management | os name **
  initial_os_release() {
    # setup global variables
    PY_INST_DIR="$REAL_HOME/.local/python-$PY_VERSION"
    VENV_DIR="$REAL_HOME/.venv"
    VENV_BIN="$REAL_HOME/.venv/bin/python"

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
  # Initial environment variables
  # ==============================================================================
  initial_global() {
    load_global_prop   # Load global properties (Step 1)
    initial_os_release # 初始化发行版信息
    initial_language   # 初始化语言包以支持utf8
    initial_log_file   # 初始化日志文件
  }

  # ==============================================================================
  # Initial environment: python 3.10 | install packages
  # ==============================================================================
  initial_environment() {
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
    printf "\n" >&2
    # 4. Load JSON environment variables
    # META_Command=$(json_load_data "cmd_meta") # Parse command JSON
  }

  # ==============================================================================
  # Feature 2: Configure SSH (applicable to all distributions)
  # Function: configure_sshd
  # Purpose: Check and install sshd, interactively modify SSH port and root login permissions
  # Parameters: None
  # Return Value: None (directly modifies /etc/ssh/sshd_config and restarts sshd)
  # ==============================================================================
  configure_sshd() {
    local ssh_service=$([[ $DISTRO_OSTYPE == "ubuntu" ]] && echo ssh || echo sshd)

    # Check if sshd is installed
    if ! (systemctl is-active ssh &>/dev/null || systemctl is-active sshd &>/dev/null); then
      info "sshd is not installed, installing now..."
      if [[ "$DISTRO_PM" = "zypper" || "$DISTRO_PM" = "pacman" ]]; then
        install_base_pkg "openssh" "sshd|ssh.service" "" # two steps of check
      else
        install_base_pkg "openssh-server" "sshd|ssh.service" "" # two steps of check
      fi
      systemctl enable --now "$ssh_service"
    fi

    if sh_configure_sshd; then # python adds-on: config /etc/ssh/sshd_config
      # Restart SSH service
      systemctl restart "$ssh_service"
      if [[ $? -eq 0 ]]; then
        info "SSH configuration has been applied"
      else
        warning "systemctl restart {} failed, please execute manually" "$ssh_service"
      fi
    fi
    echo
  }

  # --------------------------
  # Feature 3: Configure static IP
  # --------------------------
  configure_ip() {
    if sh_configure_nw; then # python adds-on: config network as fix ip
      init_env_nw
      network_config
    fi
    echo
  }

  # --------------------------
  # Feature 4: Install docker composer
  # --------------------------
  docker_compose() {
    init_docker_setup
    if sh_check_docker_install; then
      install_docker
    fi
    if sh_check_docker_run; then
      infra_setup
      apps_setup
    fi
  }

  # --------------------------
  # Feature 5: Close resources
  # --------------------------
  close_all() {
    destroy_temp_files
    stty sane # Reset terminal settings
    sh_clear_cache
  }

  # ==============================================================================
  # Main Function
  # ==============================================================================
  init_main() {
    initial_global # Set environment variables
    echo -e "\n=== $INIT_SYSTEM_START - $PRETTY_NAME ===\n"
    trap 'close_all' EXIT
    initial_environment # Initialize basic values
    configure_sshd      # Configure SSH
    configure_ip        # Configure static IP
    docker_compose      # Install Docker software
    trap - EXIT
    close_all # close python cache
    echo -e "\n=== $INIT_SYSTEM_END - $PRETTY_NAME ==="
  }

  # ==============================================================================
  # Description: Ensure script is run as root via sudo
  # 功能：强制脚本以 root（sudo）身份运行，否则自动重新调用自己
  # ==============================================================================
  require_sudo() {
    # Run as root
    if [[ "$EUID" -ne 0 ]]; then
      load_global_prop # Load global properties (Step 1)
      warning -i "$INIT_SUDO_RUN"
      ENV_VARS_TO_PASS=(
        REAL_USER="$USER"
        REAL_HOME="$HOME"
        TIMEOUT_FILE="${TIMEOUT_FILE:-}"
        PARAM_FILE="${PARAM_FILE:-}"
      )
      exec sudo env "${ENV_VARS_TO_PASS[@]}" "$0" "$@"
    else
      [[ -z "${REAL_USER:-}" ]] && {
        export REAL_USER="$USER"
        export REAL_HOME="$HOME"
        export TIMEOUT_FILE="${TIMEOUT_FILE:-}"
        export PARAM_FILE="${PARAM_FILE:-}"
      }
    fi
    # Ensure old process is terminated
    if [[ -z "${REAL_USER:-}" ]]; then
      echo "System Error: REAL_USER has no value, exiting."
      exit 1
    fi
  }

  show_version() {
    load_global_prop # Load global properties (Step 1)
    local version="zoomit v1.0"
    local year="2005"
    local author="sj7112"
    echo
    string -i "$VERSION_CLAIM" "$version" "$year" "$author"
    echo
  }

  # ==============================================================================
  # Main Function
  # -v | --version      show version info.
  # -t5 | --timeout=5   5 seconds timeout
  # --fixip=110         last octet of fix IP
  # ==============================================================================
  if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Check for --version or -v argument
    TEMP=$(getopt -o vt: --long version,timeout:,lang:,fixip: -n 'script' -- "$@")
    if [ $? != 0 ]; then
      echo "Parameter Error!" >&2
      exit 1
    fi

    eval set -- "$TEMP"

    while true; do
      case "$1" in
        -v | --version)
          show_version
          exit 0
          ;;
        -t | --timeout)
          init_time_out "$2" # Initialize timeout value
          shift 2
          ;;
        --lang)
          init_param_lang "$2" # Default shell language
          shift 2
          ;;
        --fixip)
          init_param_fixip "$2" # Fixed IP address
          shift 2
          ;;
        --)
          shift
          break
          ;;
        *)
          echo "Parameter Error!"
          exit 1
          ;;
      esac
    done

    require_sudo "$@" # Force the main script to run with sudo
    init_main "$@"    # Execute as root
  fi

fi
