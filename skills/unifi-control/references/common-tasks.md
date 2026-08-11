# Common UniFi tasks — copy-paste recipes

Recipes for frequent jobs. Curated tools are preferred where they exist; these
cover the long tail via `unifi_call`. **Reads are safe; confirm writes with the
user first.**

## Who's on my network / find a device

```
unifi_clients(active_only=True)          # connected now (name, ip, mac, signal, usage)
unifi_clients(active_only=False)         # all known clients incl. offline
unifi_devices()                          # APs / switches / gateway
unifi_devices(mac="aa:bb:cc:dd:ee:ff")   # one device, full detail
```

## Is the internet/network healthy?

```
unifi_status()      # WAN ip, ISP, up/down, device+client counts, gateway CPU/mem
unifi_health()      # per-subsystem ok/warning/error
unifi_dashboard()   # rich overview: wifi doctor, wan routability, most-active, retries
unifi_alarms()      # open alerts
unifi_events(limit=20)   # recent connects/disconnects/WAN events
```

## Why won't a device connect / why is Wi-Fi flaky?

```
unifi_wifi_connectivity()   # assoc/auth/DHCP/DNS success ratios + recent FAILED events
# low ratio pinpoints the stage: DHCP fails -> pool/relay; auth fails -> PSK/RADIUS
unifi_clients(active_only=True)   # then check the client's signal / AP
unifi_dashboard()           # wifi doctor, TX retries, radio density
```
Live per-client ping (`ping/{mac}`) is WebSocket-only and has no curated tool — use
the UI's client Connection panel for continuous latency to one device.

## Speedtest

```
unifi_run_speedtest(confirm=True)   # trigger (uses bandwidth ~30s)
unifi_speedtest_status()            # poll: download/upload Mbps, latency
```

## Block / unblock / reconnect a client

```
unifi_client_block(mac="<mac>", confirm=True)
unifi_client_unblock(mac="<mac>", confirm=True)
unifi_client_reconnect(mac="<mac>", confirm=True)   # kick-sta, forces re-associate
```
Equivalent raw form: `unifi_call("cmd/stamgr", method="POST", json={"cmd":"block-sta","mac":"<mac>"})`

## Rename / set fixed IP for a client (read-modify-write rest/user)

```
# 1. find the object
unifi_clients(active_only=False)     # note the client's _id
# 2. read the full object, then PUT it back with changes
obj = unifi_call("rest/user/<_id>")["data"][0]
obj["name"] = "Living Room TV"
obj["use_fixedip"] = True
obj["fixed_ip"] = "192.168.0.50"
obj["network_id"] = "<lan network _id>"     # required with fixed IP
unifi_call("rest/user/<_id>", method="PUT", json=obj)   # confirm first
```

## Wireless (SSID)

```
unifi_wlans()                                        # list SSIDs + _id
unifi_wlan_set_enabled("<wlan _id>", enabled=False, confirm=True)   # disable an SSID
# change PSK: read-modify-write rest/wlanconf
w = unifi_call("rest/wlanconf/<_id>")["data"][0]
w["x_passphrase"] = "newStrongPassword"
unifi_call("rest/wlanconf/<_id>", method="PUT", json=w)   # confirm first
```

## Firewall (this box = zone-based v2)

```
unifi_firewall_policies()             # the ACTIVE firewall (85 policies)
unifi_firewall_groups()               # address/port groups
unifi_firewall_policy_set_enabled("<_id>", enabled=False, confirm=True)  # toggle (curated RMW)
# edit other policy fields: read-modify-write via v2
pols = unifi_call("firewall-policies", surface="v2")["data"]
p = next(x for x in pols if x["name"] == "Block IoT to LAN")
p["enabled"] = False
unifi_call(f"firewall-policies/{p['_id']}", method="PUT", surface="v2", json=p)  # confirm
```
Classic rules (`unifi_firewall_rules`) are empty here — only relevant on older setups.

## Port forwarding

```
unifi_port_forwards()                 # list + _id
unifi_port_forward_set_enabled("<_id>", enabled=True, confirm=True)
# create one (confirm first):
unifi_call("rest/portforward", method="POST", json={
  "name":"Web","enabled":True,"proto":"tcp","src":"any",
  "dst_port":"443","fwd":"192.168.0.20","fwd_port":"443"})
```

## Traffic rules (block apps/domains, e.g. parental controls)

```
unifi_traffic_rules()
unifi_traffic_rule_set_enabled("<_id>", enabled=True, confirm=True)
```

## Networks / VLANs

```
unifi_networks()                      # list LAN/VLAN/WAN + _id, subnet, DHCP
# create a VLAN (confirm first):
unifi_call("rest/networkconf", method="POST", json={
  "name":"IoT","purpose":"corporate","vlan_enabled":True,"vlan":30,
  "ip_subnet":"192.168.30.1/24","dhcpd_enabled":True,
  "dhcpd_start":"192.168.30.6","dhcpd_stop":"192.168.30.254"})
```

## Restart / locate a device

```
unifi_device_restart(mac="<mac>", confirm=True)   # ⚠ gateway restart = whole net down
unifi_device_locate(mac="<mac>", on=True, confirm=True)   # flash LED to find it
unifi_device_port_cycle(mac="<switch mac>", port_idx=5, confirm=True)  # PoE power-cycle
```

## Guest / hotspot

```
unifi_call("stat/guest")                                  # current authorizations
unifi_call("cmd/stamgr", method="POST",
           json={"cmd":"authorize-guest","mac":"<mac>","minutes":120})   # confirm
unifi_call("stat/voucher")                                # vouchers
```

## Settings (read any section, write by key)

```
unifi_settings()                      # every section
unifi_settings(key="mgmt")            # one section
# write: unifi_call("set/setting/<key>", method="POST", json={...})  # confirm
```

## Anything else

```
unifi_list_endpoints("radius")        # discover the endpoint
unifi_call("rest/account")            # read it to learn the shape
```
