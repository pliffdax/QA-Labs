#!/bin/sh
# Apply the lease only to the isolated client interface.
[ "$interface" = b0 ] || exit 1
case "$reason" in
  PREINIT) ip link set dev "$interface" up ;;
  BOUND|RENEW|REBIND|REBOOT)
    ip -4 addr replace "$new_ip_address/$new_subnet_mask" dev "$interface" valid_lft "$new_dhcp_lease_time" preferred_lft "$new_dhcp_lease_time" || exit 1
    for router in $new_routers; do
      ip -4 route replace default via "$router" dev "$interface" || exit 1
      break
    done
    : > /run/qa3520-resolv.conf
    for server in $new_domain_name_servers; do
      echo "nameserver $server" >> /run/qa3520-resolv.conf
    done
    ;;
  RELEASE|EXPIRE|STOP)
    [ -z "$old_ip_address" ] || ip -4 addr del "$old_ip_address/$old_subnet_mask" dev "$interface"
    ;;
esac
exit 0
