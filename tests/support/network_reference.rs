// Test harness only. Packet parsing, aggregation and Linux ownership lookup are
// compiled directly from the pinned upstream checkouts, without modifying them.
use std::{collections::HashMap, io::{self, Read}, net::IpAddr};
use pnet::{datalink::{DataLinkReceiver, NetworkInterface}, ipnetwork::IpNetwork};
use serde_json::{json, Value};
use sniffnet_packet_parser::{LinkType, ParsedPacket};

mod network {
    #[path = "@BANDWHICH@/src/network/connection.rs"] mod connection;
    #[path = "@BANDWHICH@/src/network/sniffer.rs"] mod sniffer;
    #[path = "@BANDWHICH@/src/network/utilization.rs"] mod utilization;
    pub use connection::*;
    pub use sniffer::*;
    pub use utilization::*;
}
mod os {
    #[derive(Clone)]
    pub struct ProcessInfo { pub name: String, pub pid: u32 }
    impl ProcessInfo {
        pub fn new(name: &str, pid: u32) -> Self { Self { name: name.into(), pid } }
    }
    #[path = "@BANDWHICH@/src/os/linux.rs"] pub mod linux;
    pub mod shared {
        pub fn get_datalink_channel(_: &pnet::datalink::NetworkInterface) -> std::io::Result<Box<dyn pnet::datalink::DataLinkReceiver>> {
            Err(std::io::Error::other("fixture receiver cannot reopen an interface"))
        }
    }
}
pub struct OpenSockets { pub sockets_to_procs: HashMap<network::LocalSocket, os::ProcessInfo> }
mod sniffnet_lookup {
    use std::sync::mpsc::{Receiver, Sender};
    use listeners::{Process, Protocol};
    @SNIFFNET_LOOKUP@
}
struct Frame(Vec<u8>);
impl DataLinkReceiver for Frame {
    fn next(&mut self) -> io::Result<&[u8]> { Ok(&self.0) }
}

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    let request: Value = serde_json::from_str(&input).unwrap();
    let mut output = Vec::new();
    let mut utilization = network::Utilization::new();
    for frame in request["frames"].as_array().unwrap() {
        let hex = frame["hex"].as_str().unwrap();
        let bytes: Vec<u8> = (0..hex.len()).step_by(2).map(|i| u8::from_str_radix(&hex[i..i+2], 16).unwrap()).collect();
        let ips: Vec<IpNetwork> = frame["local"].as_array().unwrap().iter().map(|ip| {
            let address: IpAddr = ip.as_str().unwrap().parse().unwrap();
            IpNetwork::new(address, if address.is_ipv4() {32} else {128}).unwrap()
        }).collect();
        let interface = NetworkInterface { name: "fixture".into(), description: "fixture".into(), index: 1, mac: None, ips, flags: 0 };
        let mut sniffer = network::Sniffer::new(interface, Box::new(Frame(bytes.clone())), true);
        let bandwhich = sniffer.next().map(|segment| {
            let value = json!({"bytes": segment.data_length, "direction": format!("{:?}", segment.direction),
                "localAddress": segment.connection.local_socket.ip.to_string(), "localPort": segment.connection.local_socket.port,
                "remoteAddress": segment.connection.remote_socket.ip.to_string(), "remotePort": segment.connection.remote_socket.port,
                "protocol": format!("{}", segment.connection.local_socket.protocol)});
            utilization.ingest(segment);
            value
        });
        let link = frame["link"].as_i64().unwrap() as i32;
        let sniffnet = ParsedPacket::from_bytes(&bytes, LinkType::from_pcap(pcap::Linktype(if link == 101 {12} else {link}))).map(|parsed| {
            json!({"bytes": parsed.bytes_count(), "source": parsed.net_info.src_ip.to_string(), "destination": parsed.net_info.dst_ip.to_string(),
                "sourcePort": parsed.transport_info.src_port, "destinationPort": parsed.transport_info.dst_port,
                "protocol": format!("{:?}", parsed.transport_info.protocol)})
        });
        output.push(json!({"bandwhich": bandwhich, "sniffnet": sniffnet}));
    }
    let totals: Vec<_> = utilization.connections.iter().map(|(connection, info)| json!({
        "connection": format!("{:?}", connection), "sent": info.total_bytes_uploaded, "received": info.total_bytes_downloaded
    })).collect();
    let ports: Vec<u16> = request["ports"].as_array().unwrap().iter().map(|p| p.as_u64().unwrap() as u16).collect();
    let owners: Vec<_> = os::linux::get_open_sockets().sockets_to_procs.iter().filter(|(key,_)| ports.contains(&key.port)).map(|(key, process)| {
        json!({"address": key.ip.to_string(), "port": key.port, "protocol": key.protocol.to_string(), "pid": process.pid, "name": process.name})
    }).collect();
    let (request_tx, request_rx) = std::sync::mpsc::channel();
    let (response_tx, response_rx) = std::sync::mpsc::channel();
    let lookup = std::thread::spawn(move || sniffnet_lookup::lookup_program(&request_rx, &response_tx));
    for port in &ports { request_tx.send((*port, listeners::Protocol::TCP)).unwrap(); }
    drop(request_tx);
    let sniffnet_owners: Vec<_> = response_rx.iter().map(|(port, _, process)| json!({
        "port": port, "pid": process.map(|p| p.pid)
    })).collect();
    lookup.join().unwrap();
    println!("{}", json!({"frames": output, "bandwhichTotals": totals, "owners": owners, "sniffnetOwners": sniffnet_owners}));
}
