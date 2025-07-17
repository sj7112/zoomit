#!/bin/bash

# Load once only
if [[ -z "${LOADED_NETWORK:-}" ]]; then
  LOADED_NETWORK=1

  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # lib direcotry
  : ENV_NW_PATH="$(dirname "$LIB_DIR")/config/network/.env"     # system config direcotry

  LOG_FILE="/var/log/sj_install.log"
  SWITCH_FILE="/tmp/switch_network.sh"
  RESULT_FILE="/tmp/switch_network.result"

  # Initialization function: Read the .env object passed by Python and initialize
  init_env_nw() {
    while IFS='=' read -r key value; do
      [[ -z "$key" || "$key" == '#' ]] && continue
      # Store in different arrays based on section
      ENV_NETWORK["$key"]="$value"
      keys_network+=("$key")
    done <"$ENV_NW_PATH"
  }

  # ==============================================================================
  # Part 1: add header to auto switch network script
  # ==============================================================================
  cat_header() {
    cat >"$SWITCH_FILE" <<EOF
#!/bin/bash

exec >> "$LOG_FILE" 2>&1  # add to log data

set -x
echo "=== Switch Network start - \$(date) ==="

EOF
  }

  # ==============================================================================
  # Part 3: add footer to auto switch network script
  # ==============================================================================
  cat_footer() {
    NW_SUCC=$(_mf "[{}] Network switched. Log: {}" "$MSG_SUCCESS" "$LOG_FILE")
    NW_FAIL=$(_mf "[{}] Failed to switch network. Log: {}" "$MSG_ERROR" "$LOG_FILE")
    DEBUG_CMT=$([[ "${DEBUG:-1}" == "0" ]] && echo "# " || echo "")

    cat >>"$SWITCH_FILE" <<EOF
if [ \$? -eq 0 ]; then
  echo "$NW_SUCC" | tee -a "$LOG_FILE" > "$RESULT_FILE"
  sed -i 's/^HAS_STATIC=.*/HAS_STATIC=active/' "$ENV_NW_PATH"
else
  echo "$NW_FAIL" | tee -a "$LOG_FILE" > "$RESULT_FILE"
  exit 1
fi

echo "=== Switch Network end - \$(date) ==="

# clean up
${DEBUG_CMT}rm -f "$SWITCH_FILE"
EOF
  }

  # ==============================================================================
  # Countdown function
  # ==============================================================================
  count_down() {
    # Set environment variables
    local count=5
    local IFACE="${ENV_NETWORK["MAIN_IFACE"]}"
    local IP_ADDR="${ENV_NETWORK["STATIC_IP"]}"

    # ANSI color
    local BG_BLUE="\033[44m"
    local NC="\033[0m" # reset color

    info "Change network in {} seconds: {} (interface {}). Please be ready to reconnect. Press Ctrl+C to cancel" "$count" "$IP_ADDR" "$IFACE"
    for i in $(seq "$count" -1 1); do
      echo -ne "${BG_BLUE}  $i 秒 ${NC}\r"
      sleep 0.5
    done
    echo -e "${BG_BLUE}  0 秒 ${NC}"

    chmod +x "$SWITCH_FILE"            # Add execute permission
    setsid "$SWITCH_FILE" </dev/null & # Execute the script (setsid prevents hanging)

    # # 重载配置并重启 networkd
    # count_down # Countdown reminder
    # if ! systemctl restart systemd-networkd; then
    #   exiterr "Failed to restart systemd-networkd. Please check and try again"
    # fi
  }

  # ==============================================================================
  # Configure Static IP (NetworkManager)
  # check connection: nmcli connection show
  # check config file: /etc/netplan/90-uuid.yaml
  # ==============================================================================
  config_nmcli() {
    # Set environment variables
    IFACE="${ENV_NETWORK["MAIN_IFACE"]}"  # Network interface name
    CON_NAME="static-$IFACE"              # Connection name, used to identify the configuration in NetworkManager
    IP_ADDR="${ENV_NETWORK["STATIC_IP"]}" # IP address (without subnet mask)
    PREFIX="${ENV_NETWORK["PREFIX"]:-24}" # Subnet mask length, default is 24
    GATEWAY="${ENV_NETWORK["GATEWAY"]}"   # Gateway
    DNS="${ENV_NETWORK["DNS_SERVERS"]}"   # DNS servers, separated by spaces

    # Create the script - Main part
    cat >>"$SWITCH_FILE" <<EOF
# 1. Check if the connection exists, delete it if not
if ! nmcli connection show "$CON_NAME" &>/dev/null; then
  nmcli connection delete "$CON_NAME" &>/dev/null || true
fi

# 2. add the connection to use a static IP
nmcli connection add type ethernet ifname "$IFACE" con-name "$CON_NAME" \\
  ipv4.addresses "$IP_ADDR/$PREFIX" \\
  ipv4.gateway "$GATEWAY" \\
  ipv4.dns "$DNS" \\
  ipv4.method manual \\
  connection.autoconnect yes

# 3. Activate the connection
nmcli connection up "$CON_NAME"
EOF
  }

  # ==============================================================================
  # 配置静态IP（ifupdown -> systemd_networkd）
  # ==============================================================================
  ifupdown_to_systemd_networkd() {
    install_base_pkg "systemd" "systemctl" # install systemd-networkd

    IFACE="${ENV_NETWORK["MAIN_IFACE"]}"  # Network interface name
    IP_ADDR="${ENV_NETWORK["STATIC_IP"]}" # IP address (without subnet mask)
    PREFIX="${ENV_NETWORK["PREFIX"]:-24}" # Subnet mask length, default is 24
    GATEWAY="${ENV_NETWORK["GATEWAY"]}"   # Gateway
    DNS="${ENV_NETWORK["DNS_SERVERS"]}"   # DNS servers, separated by spaces
    local NETDIR="/etc/systemd/network"
    local NET_FILE="$NETDIR/10-$IFACE.network"

    # shellcheck disable=SC2086
    local DNS_CONFIG=$(printf 'DNS=%s\n' $DNS)

    # Create the script - Main part
    cat >>"$SWITCH_FILE" <<EOF
# ----------- Part 1: comment ifupdown -----------
IFACE="${ENV_NETWORK["MAIN_IFACE"]}"
NET_FILE="/etc/network/interfaces"

if [[ -f "$NET_FILE" ]]; then
  cp -a "$NET_FILE" "${NET_FILE}.\$(date +%Y%m%d_%H%M%S)"
  sed -i "/^[[:space:]]*allow-hotplug.*$IFACE/s/^/# /" "$NET_FILE"
  sed -i "/^[[:space:]]*iface.*$IFACE/s/^/# /" "$NET_FILE"
fi

# ----------- Part 2: config systemd-networkd -----------
if [[ -f "$NET_FILE" ]]; then
  cp -a "$NET_FILE" "$NET_FILE.\$(date +%Y%m%d_%H%M%S)"
else
  mkdir -p "$NETDIR"
fi

cat > "$NET_FILE" <<EOL
[Match]
Name=$IFACE

[Network]
DHCP=no
Address=$IP_ADDR/$PREFIX
Gateway=$GATEWAY
$DNS_CONFIG
EOL
# ----------- Part 3: switch systemd-networkd -----------
systemctl stop networking
systemctl disable networking
pkill dhclient || true
pkill dhcpcd || true
systemctl enable systemd-networkd
systemctl start systemd-networkd
systemctl enable systemd-resolved
systemctl start systemd-resolved
systemctl restart systemd-networkd
EOF
  }

  # ==============================================================================
  # Config fixed IP (systemd_networkd)
  # check DNS: networkctl status | grep -A 4 DNS
  # ==============================================================================
  config_systemd_networkd() {
    IFACE="${ENV_NETWORK["MAIN_IFACE"]}"  # Network interface name
    IP_ADDR="${ENV_NETWORK["STATIC_IP"]}" # IP address (without subnet mask)
    PREFIX="${ENV_NETWORK["PREFIX"]:-24}" # Subnet mask length, default is 24
    GATEWAY="${ENV_NETWORK["GATEWAY"]}"   # Gateway
    DNS="${ENV_NETWORK["DNS_SERVERS"]}"   # DNS servers, separated by spaces
    local NETDIR="/etc/systemd/network"
    local NET_FILE="$NETDIR/10-$IFACE.network" # 例如：/etc/systemd/network/10-ens192.network

    # shellcheck disable=SC2086
    local DNS_CONFIG=$(printf 'DNS=%s\n' $DNS)

    # Create the script - Main part
    cat >>"$SWITCH_FILE" <<EOF
# ----------- Part 2: config systemd-networkd -----------
if [[ -f "$NET_FILE" ]]; then
  cp -a "$NET_FILE" "$NET_FILE.\$(date +%Y%m%d_%H%M%S)"
else
  mkdir -p "$NETDIR"
fi

DNS_CONFIG=\$(printf "DNS=%s\\n" \$DNS)

cat > "$NET_FILE" <<EOL
[Match]
Name=$IFACE

[Network]
DHCP=no
Address=$IP_ADDR/$PREFIX
Gateway=$GATEWAY
$DNS_CONFIG
EOL
# ----------- Part 3: switch systemd-networkd -----------
systemctl enable systemd-resolved
systemctl start systemd-resolved
systemctl restart systemd-networkd
EOF
  }

  # ==============================================================================
  # main function: network configuration
  # ==============================================================================
  network_config() {
    # Part 1: Create the script - header
    cat_header

    if [[ ${ENV_NETWORK["CURR_NM"]} == "NetworkManager" ]]; then
      string "NetworkManager is running (systemctl status NetworkManager)"
      config_nmcli
    elif [[ ${ENV_NETWORK["CURR_NM"]} == "networking" ]]; then
      string "ifupdown is running (systemctl status networking)"
      ifupdown_to_systemd_networkd
    elif [[ ${ENV_NETWORK["CURR_NM"]} == "wicked" ]]; then
      string "wicked is running (systemctl status wicked)"
      # wicked_to_systemd_networkd
    elif [[ ${ENV_NETWORK["CURR_NM"]} == "network" ]]; then
      string "network-scripts is running (systemctl status network)"
      # network_to_systemd_networkd
    elif [[ ${ENV_NETWORK["CURR_NM"]} == "systemd-networkd" ]]; then
      # /etc/systemd/network/10-$IFACE.network
      string "systemd-networkd is running (systemctl status systemd-networkd)"
      config_systemd_networkd
    else
      exiterr "Unknown network manager. Unable to configure static IP"
    fi

    # Part 3: Create the script - footer
    cat_footer

    # execute the script in the background
    count_down # Countdown reminder
  }

fi
