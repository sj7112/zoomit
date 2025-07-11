#!/bin/bash

# Load once only
if [[ -z "${LOADED_DOCKER_INSTALL:-}" ]]; then
  LOADED_DOCKER_INSTALL=1

  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # lib direcotry
  : "${CONF_DIR:=$(dirname "$LIB_DIR")/config}"                 # config directory

  LOG_FILE="/var/log/sj_install.log"

  # Detect system architecture and distribution
  get_docker_compose_url() {
    local arch=$(uname -m) # Detect architecture
    case "$arch" in
      aarch64 | arm64) arch="aarch64" ;;
      armv7l) arch="armv7" ;;
    esac
    echo "https://github.com/docker/compose/releases/download/v2.36.2/docker-compose-linux-${arch}"
  }

  check_docker() {
    # Check docker
    docker_ver=$(docker --version 2>/dev/null | awk '{print $3}' | sed 's/,//')
    [[ -n "$docker_ver" ]] || exiterr "Docker 安装失败"

    # Check docker compose (try v2 first)
    if docker compose version &>/dev/null; then
      compose_ver="v2"
    elif command -v docker-compose &>/dev/null; then
      compose_ver="v1"
    else
      exiterr "Docker Compose 安装失败，请尝试手动安装 \
路径: {}" "$(get_docker_compose_url)"
    fi

    string "Docker ({}) 与 Docker Compose ({}) 已安装" "$docker_ver" "$compose_ver"
  }

  # ==============================================================================
  # remove docker
  # ==============================================================================
  remove_docker_apt() {
    if dpkg -l | grep -qw docker.io; then
      string "Uninstalling {}..." "docker.io" | tee -a "$LOG_FILE"
      apt-get remove -y docker.io docker-compose-plugin >>"$LOG_FILE" 2>&1
    fi

    if dpkg -l | grep -qw docker-ce; then
      string "Uninstalling {}..." "docker-ce" | tee -a "$LOG_FILE"
      apt-get remove -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >>"$LOG_FILE" 2>&1
    fi
  }

  remove_docker_rpm() {
    if rpm -q docker-ce >/dev/null 2>&1 || rpm -q docker >/dev/null 2>&1; then
      string "Uninstalling {}..." "docker-ce" | tee -a "$LOG_FILE"
      $DISTRO_PM remove -y docker-ce docker-ce-cli containerd.io docker-compose-plugin docker >>"$LOG_FILE" 2>&1
    fi
  }

  remove_docker_zypper() {
    if rpm -q docker >/dev/null 2>&1; then
      string "Uninstalling {}..." "docker (zypper)" | tee -a "$LOG_FILE"
      zypper remove -y docker docker-compose >>"$LOG_FILE" 2>&1
    fi
  }

  remove_docker_pacman() {
    if pacman -Qs docker >/dev/null 2>&1; then
      string "Uninstalling {}..." "docker (pacman)" | tee -a "$LOG_FILE"
      pacman -Rs --noconfirm docker docker-compose >>"$LOG_FILE" 2>&1
    fi
  }

  # ==============================================================================
  # official installation docker-ce
  # ==============================================================================
  install_docker_off_apt() {
    remove_docker_apt # remove original version if exists

    info "在 {} 上安装 Docker 与 Docker Compose..." "$DISTRO_OSTYPE"

    # 安装依赖
    install_base_pkg "ca-certificates" "/etc/ssl/certs/|/etc/pki/tls/|/etc/ssl/cert.pem"
    install_base_pkg "curl"
    install_base_pkg "gnupg" ""               # no need to check
    install_base_pkg "lsb-release" ""         # no need to check
    install_base_pkg "apt-transport-https" "" # no need to check (obsoleted)

    # 添加 Docker 仓库 GPG（可选，但推荐）
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/$DISTRO_OSTYPE/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # 添加 Docker 仓库源
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/$DISTRO_OSTYPE $DISTRO_CODENAME stable" \
      >/etc/apt/sources.list.d/docker.list

    # 安装 Docker
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # # 验证 Docker 是否成功安装
    # docker --version &>/dev/null || exiterr "Docker 安装失败"
    # docker compose version &>/dev/null || exiterr "Docker compose v2 插件安装失败"
  }

  install_docker_off_rpm() {
    remove_docker_rpm # remove original version if exists

    info "Installing Docker and Docker Compose on {}..." "$DISTRO_OSTYPE"

    # 安装依赖
    install_base_pkg "yum-utils" ""                     # no need to check
    install_base_pkg "device-mapper-persistent-data" "" # no need to check
    install_base_pkg "lvm2" ""                          # no need to check (obsoleted)

    # 添加 Docker YUM 仓库
    yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

    # 安装 Docker
    yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # 启动 Docker 并设置开机启动
    systemctl enable --now docker

    # # 验证 Docker 是否成功安装
    # docker --version &>/dev/null || exiterr "Docker installation failed"
    # docker compose version &>/dev/null || exiterr "Docker Compose v2 plugin installation failed"
  }

  # ==============================================================================
  # use package management to install docker
  # ==============================================================================
  install_docker_pm() {
    info "在 {} 上安装 Docker 与 Docker Compose..." "$DISTRO_OSTYPE"

    case "$DISTRO_OSTYPE" in
      debian | ubuntu)
        echo "test1"
        remove_docker_apt # remove original version if exists
        echo "test2"
        install_base_pkg docker.io ""
        echo "test3"
        install_base_pkg docker-compose ""
        echo "test4"
        ;;
      centos | rhel)
        remove_docker_rpm # remove original version if exists
        install_base_pkg docker ""
        install_base_pkg docker-compose-plugin ""
        ;;
      opensuse)
        remove_docker_zypper
        install_base_pkg docker ""
        install_base_pkg docker-compose ""
        ;;
      arch)
        remove_docker_pacman
        install_base_pkg docker ""
        install_base_pkg docker-compose ""
        ;;
      *) exiterr -i "$INIT_LINUX_UNSUPPORT: $ID ($PRETTY_NAME)" ;;
    esac
    systemctl enable --now docker
    # systemctl start docker

    # # 验证 Docker 是否成功安装
    # docker --version &>/dev/null || exiterr "Docker 安装失败"

    # # 检查是否已包含 docker compose 插件（v2）
    # if ! check_compose_v2; then
    #   COMPOSE_PLUGIN_DIR="/usr/lib/docker/cli-plugins"
    #   mkdir -p "$COMPOSE_PLUGIN_DIR"

    #   curl -sSL https://github.com/docker/compose/releases/download/v2.24.6/docker-compose-linux-x86_64 \
    #     -o "$COMPOSE_PLUGIN_DIR/docker-compose"
    #   sudo chmod +x "$COMPOSE_PLUGIN_DIR/docker-compose"
    # fi

    # # 验证 Compose 是否就绪
    # if ! docker compose version &>/dev/null; then
    #   error "Docker Compose 安装失败"
    #   return 1
    # fi

    # success "Docker 与 Docker Compose 安装完成！"
  }

  # ==============================================================================
  # use official website to install docker
  # ==============================================================================
  install_docker_official() {
    case "$DISTRO_PM" in
      apt) install_docker_off_apt ;;       # Debian | Ubuntu
      yum | dnf) install_docker_off_rpm ;; # CentOS | RHEL
    esac
  }

fi
