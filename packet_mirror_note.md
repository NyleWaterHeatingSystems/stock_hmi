# HPC packet mirror (on hold)

On hold since 2026-11-03, waiting for more information from the requester. Not merged, and not run on real hardware.

## The request

Forward eth0 to eth1 on ports 2324, 2325 and 2326 to expose the status and control packets between the HMI and the
HPC. It should be created by the OS setup script, and persist through power cycles and updates of the HPC and HMI.

## What this branch does

`configure_packet_mirror()` in `stock-hmi.py` installs `/usr/local/sbin/hpc-packet-mirror` and
`hpc-packet-mirror.service`. The service reads eth0, reassembles fragments, and re-sends every UDP datagram from the
HPC (`192.168.0.2`) to the HMI (`192.168.0.3`) to `MIRROR_ADDRESS`, on the HPC's source port. A listener opens UDP
2326 on a `192.168.1.x` address and sees the same bytes the HMI received, from `192.168.1.(unit + 1)`.

Tested in network namespaces with the real generated script, with normal and swapped NIC names: copies identical at
100 Hz, fragmented datagrams, padded frames, HPC link loss, MCP cable removal, unit number change. HMI to HPC traffic
was not copied, and nothing reached the BMS network.

## Why it ended up this way

- **Not a forward.** HMI and HPC traffic is local to the HMI, so a forward never sees it. It also lets outside devices
  reach the IoT board, which keeps one return address per port: a packet from an outside device on 2326 takes status
  away from the HMI, and its commands fight the HMI's. Forwarding 2324 also hides the HMI's own proxy from the MCP
  network, which breaks `hpc-gateway`.
- **Not `tc mirred`.** A copy needs a new address. A kernel mirror can only re-address the first fragment, the IoT
  board sends up to 4096 bytes at once, and it would have to name the MCP port. eth1 and eth2 can swap names; here,
  routing finds the port from `MIRROR_ADDRESS`.

## To do before merging

- **Limit to 2326 if staying on broadcast.** This branch still copies all UDP. A copy keeps its port number, so a
  broadcast copy on 2323 or 2324 reaches the console or proxy on every HMI, including the sender, which could take
  over the proxy's return address and be read as a request. Nothing is sent on those ports today (the HMI only uses
  them with `USE_RPC`), so limiting loses nothing. A single listener IP avoids this too, but several devices may need
  to listen.
- **Check MCP devices cope with broadcast**: about 100 packets per second, roughly 0.45 Mbit/s. Multicast is the
  fallback, but needs setup on the HMI and each listener.
- **`VERSION`**: 1.1.0 was proposed, since this adds configuration; left unchanged for now.
- **A release newer than v2.0.8** is needed: `make-usb-kit.py` refuses v2.0.8, and `hpc-releases` has nothing newer.
- **Test on hardware**, across power cycles of the HMI and the HPC.

## Questions for the requester

1. Do they only need to read the status data, or also send to the HPC? Reading suits a mirror; sending needs a
   different approach, going through the HMI's proxy on 2324 so the HMI stays in control.
2. What device or software will read the data, and how many will listen?
3. Do they need every status packet, or would periodic values do? If periodic is enough, `hpc-gateway` may already
   cover it, with no mirror needed.
4. Do they need what the HMI sends, or is what the HPC reports having received enough? The `echo_iot_*` and
   `setting_*` status fields show the latter, and copying HMI to HPC traffic is not implemented.
5. Can devices on the MCP network cope with the broadcast traffic?

## hpc-gateway

`hpc-gateway` doesn't read status packets. It polls the HMI's variable proxy on 2324, so it doesn't use the mirror and
works alongside it. Leave it unchanged unless every packet is needed; a `source = mirror` mode would be about 150 to
250 lines, with a different Modbus map, and must filter by unit. It needs these changes for the new firmware either way:

- `hmi_addr` must be `192.168.1.(unit + 1)`. The example `192.168.1.20` only works for unit 19; unit 1 is `.2`.
- Run `--remap` after the HMI update. Saved rows hold table indexes, so a stale conf reports wrong values as fresh
  with no error, and Modbus addresses can change too.
- A startup check that refuses a stale conf is proposed, to be decided later.
