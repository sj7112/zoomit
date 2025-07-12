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
    [[ -n "$docker_ver" ]] || exiterr "Docker installation failure"

    # Check docker compose (try v2 first)
    if docker compose version &>/dev/null; then
      compose_ver="v2"
    elif command -v docker-compose &>/dev/null; then
      compose_ver="v1"
    else
      exiterr "Docker Compose installation failure，please try manual installation \
Github Path: {}" "$(get_docker_compose_url)"
    fi

    string "Docker ({}) and Docker Compose ({}) are installed" "$docker_ver" "$compose_ver"
  }

  # ==============================================================================
  # remove docker
  # ==============================================================================
  remove_docker_apt() {
    if dpkg -s docker.io &>/dev/null; then
      string "Uninstalling {}..." "docker.io" | tee -a "$LOG_FILE"
      apt-get purge -y docker-compose >>"$LOG_FILE" 2>&1
      apt-get purge -y docker.io >>"$LOG_FILE" 2>&1
    fi
    if dpkg -s docker-ce &>/dev/null; then
      string "Uninstalling {}..." "docker-ce" | tee -a "$LOG_FILE"
      apt-get purge -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >>"$LOG_FILE" 2>&1
    fi
  }

  remove_docker_rpm() {
    if rpm -q docker-ce >/dev/null 2>&1 || rpm -q docker >/dev/null 2>&1; then
      string "Uninstalling {}..." "docker-ce" | tee -a "$LOG_FILE"
      $DISTRO_PM remove -y docker-ce docker-ce-cli containerd.io docker-compose docker-compose-plugin docker >>"$LOG_FILE" 2>&1 || true

      # Manually clean configuration files
      rm -f /etc/yum.repos.d/docker-ce.repo /etc/pki/rpm-gpg/RPM-GPG-KEY-Docker

      # Clean cache
      $DISTRO_PM clean all >>"$LOG_FILE" 2>&1
    fi
  }

  remove_docker_zypper() {
    if rpm -q docker >/dev/null 2>&1; then
      string "Uninstalling {}..." "docker (zypper)" | tee -a "$LOG_FILE"
      zypper remove -y docker docker-compose >>"$LOG_FILE" 2>&1
      rm -rf /etc/docker /var/lib/docker /var/lib/containerd /etc/systemd/system/docker.service.d
    fi
  }

  remove_docker_pacman() {
    if pacman -Qs docker >/dev/null 2>&1; then
      string "Uninstalling {}..." "docker (pacman)" | tee -a "$LOG_FILE"
      pacman -Rs --noconfirm docker docker-compose >>"$LOG_FILE" 2>&1
      rm -rf /etc/docker /var/lib/docker /var/lib/containerd /etc/systemd/system/docker.service.d
    fi
  }

  # ==============================================================================
  # install docker by package management
  # ==============================================================================
  install_docker_apt() {
    remove_docker_apt
    info "Installing Docker and Docker Compose on {}..." "$DISTRO_OSTYPE"
    install_base_pkg docker.io ""
    install_base_pkg docker-compose ""
  }

  install_docker_rpm() {
    remove_docker_rpm
    info "Installing Docker and Docker Compose on {}..." "$DISTRO_OSTYPE"
    install_base_pkg docker ""
    install_base_pkg docker-compose-plugin ""
  }

  install_docker_zypper() {
    remove_docker_zypper
    info "Installing Docker and Docker Compose on {}..." "$DISTRO_OSTYPE"
    install_base_pkg docker ""
    install_base_pkg docker-compose ""
  }

  install_docker_pacman() {
    remove_docker_pacman
    info "Installing Docker and Docker Compose on {}..." "$DISTRO_OSTYPE"
    install_base_pkg docker ""
    install_base_pkg docker-compose ""
  }

  # ==============================================================================
  # official installation docker-ce
  # ==============================================================================
  install_docker_apt_office() {
    url=$1
    remove_docker_apt # remove original version if exists

    info "Installing Docker and Docker Compose on {}..." "$DISTRO_OSTYPE"

    # Install dependencies
    install_base_pkgs "ca-certificates" "curl" "gnupg" "lsb-release" "apt-transport-https"

    # 添加 Docker 仓库 GPG（可选，但推荐）
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL $url/gpg \
      | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # 添加 Docker 仓库源
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      $url $DISTRO_CODENAME stable" \
      >/etc/apt/sources.list.d/docker.list

    # Install Docker
    cmd_exec "apt-get update"
    install_base_pkgs docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  }

  install_docker_rpm_office() {
    url=$1
    remove_docker_rpm # remove original version if exists

    info "Installing Docker and Docker Compose on {}..." "$DISTRO_OSTYPE"

    # Install dependencies (Install yum-utils only if yum-config-manager is missing)
    install_base_pkgs "device-mapper-persistent-data" "lvm2"
    if ! command -v yum-config-manager >/dev/null 2>&1; then
      install_base_pkgs "yum-utils"
    fi

    # Add Docker YUM repo (always refresh to avoid outdated URLs)
    curl -fsSL $url/docker-ce.repo -o /etc/yum.repos.d/docker-ce.repo

    # Install Docker packages (auto selects correct versions for CentOS, RHEL, Rocky, Alma)
    install_base_pkgs docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    # Enable and start Docker service
    systemctl enable --now docker &>/dev/null
  }

  # ==============================================================================
  # use package management to install docker
  # ==============================================================================
  install_docker_pm() {
    case "$DISTRO_OSTYPE" in
      debian | ubuntu) install_docker_apt ;;
      centos | rhel) install_docker_rpm ;;
      opensuse) install_docker_zypper ;;
      arch) install_docker_pacman ;;
      *) exiterr -i "$INIT_LINUX_UNSUPPORT: $ID ($PRETTY_NAME)" ;;
    esac
    # Enable and start Docker
    systemctl enable --now docker &>/dev/null
  }

  # ==============================================================================
  # use official website to install docker
  # ==============================================================================
  install_docker_official() {
    url=$1
    case "$DISTRO_PM" in
      apt) install_docker_apt_office "$url" ;;       # Debian | Ubuntu
      yum | dnf) install_docker_rpm_office "$url" ;; # CentOS | RHEL
    esac
  }

fi
