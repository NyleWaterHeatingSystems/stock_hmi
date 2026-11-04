#!/bin/sh
# Expose the HPC's variable proxies on the MCP network, for hpc-gateway.
#
# Usage, on the HMI as root:
#   sh hpc-gateway-ports.sh install   # apply now and on every boot
#   sh hpc-gateway-ports.sh status
#   sh hpc-gateway-ports.sh remove
#
# Port on the HMI's MCP address     Variables   Reaches
#   UDP 2324 (the app, unchanged)   HMI         the HMI's own proxy
#   UDP 5324                        HPC IoT     192.168.0.2:2324
#   UDP 5325                        HPC control 192.168.0.2:2325
#
# The rules match addresses, not interface names. eth1 and eth2 can swap, and
# HMI apps up to v2.0.9 put the MCP address on br0 and the HPC on eth2.
# Replies leave as the HMI's own address because the HPC's gateway isn't the HMI.
# 2323 and 2326 stay closed: 2326 is the HMI's status link, and the IoT board
# sends status to whoever last wrote to it. It keeps a separate return address
# per port, so 5324 and 5325 don't disturb it, but each port serves one client.
# Nothing else is routed, even with ip_forward on.
#
# The service reapplies the rules on every boot, and app updates leave them
# alone: the app doesn't use iptables.

set -eu

HPC=192.168.0.2
MCP_NETWORK=192.168.1.0/24
SCRIPT=/usr/local/sbin/hpc-gateway-ports
UNIT=/etc/systemd/system/hpc-gateway-ports.service

clear_rules() {
  iptables -w -t nat -D PREROUTING -j HPC_GW_PRE 2>/dev/null || true
  iptables -w -t nat -D POSTROUTING -j HPC_GW_POST 2>/dev/null || true
  iptables -w -D FORWARD -j HPC_GW_FWD 2>/dev/null || true
  for chain in "nat HPC_GW_PRE" "nat HPC_GW_POST" "filter HPC_GW_FWD"; do
    set -- $chain
    iptables -w -t "$1" -F "$2" 2>/dev/null || true
    iptables -w -t "$1" -X "$2" 2>/dev/null || true
  done
}

apply_rules() {
  clear_rules
  iptables -w -t nat -N HPC_GW_PRE
  iptables -w -t nat -N HPC_GW_POST
  iptables -w -N HPC_GW_FWD

  for port in 2324 2325; do
    iptables -w -t nat -A HPC_GW_PRE -p udp -s "$MCP_NETWORK" -d "$MCP_NETWORK" \
      --dport "5${port#2}" -j DNAT --to-destination "$HPC:$port"
  done
  iptables -w -t nat -A HPC_GW_POST -m conntrack --ctstate DNAT -j MASQUERADE
  iptables -w -A HPC_GW_FWD -m conntrack --ctstate DNAT -j ACCEPT
  iptables -w -A HPC_GW_FWD -j DROP

  iptables -w -I FORWARD 1 -j HPC_GW_FWD
  iptables -w -t nat -I PREROUTING 1 -j HPC_GW_PRE
  iptables -w -t nat -I POSTROUTING 1 -j HPC_GW_POST
  sysctl -q -w net.ipv4.ip_forward=1
}

install_service() {
  command -v iptables >/dev/null || {
    echo "iptables is not installed; install it from the kit's debs/ first" >&2
    exit 1
  }
  ip -4 -o addr show | grep -q ' inet 192\.168\.1\.' ||
    echo "warning: this HMI has no 192.168.1.x address yet (no MCP cable?)" >&2
  install -m 755 -o root -g root "$0" "$SCRIPT"
  cat > "$UNIT" <<UNIT_EOF
[Unit]
Description=Expose the HPC variable proxies to hpc-gateway
After=local-fs.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=$SCRIPT apply
ExecStop=$SCRIPT clear

[Install]
WantedBy=multi-user.target
UNIT_EOF
  systemctl daemon-reload
  systemctl enable hpc-gateway-ports.service
  systemctl restart hpc-gateway-ports.service
  show_status
}

remove_service() {
  systemctl disable --now hpc-gateway-ports.service 2>/dev/null || true
  rm -f "$UNIT" "$SCRIPT"
  clear_rules
  sysctl -q -w net.ipv4.ip_forward=0
  systemctl daemon-reload
  echo "Removed hpc-gateway-ports"
}

show_status() {
  echo "service: $(systemctl is-active hpc-gateway-ports.service 2>/dev/null || true)"
  echo "ip_forward: $(sysctl -n net.ipv4.ip_forward)"
  ip -4 -o addr show | awk '{print "address: " $2, $4}' | grep ' 192\.168\.' || true
  iptables -w -t nat -S HPC_GW_PRE 2>/dev/null | grep DNAT || echo "no forward rules"
}

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root" >&2
  exit 1
fi

case "${1:-}" in
  install) install_service ;;
  apply) apply_rules ;;
  clear) clear_rules ;;
  remove) remove_service ;;
  status) show_status ;;
  *)
    echo "Usage: $0 install|status|remove" >&2
    exit 2
    ;;
esac
