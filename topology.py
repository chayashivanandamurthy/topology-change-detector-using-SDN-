from mininet.net import Mininet
from mininet.node import OVSBridge
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.topo import Topo

import threading
import time
from datetime import datetime

LOG_FILE = "topology_events.log"


class SimpleTopo(Topo):
    def build(self):
        # Hosts
        h1 = self.addHost('h1', ip='10.0.0.1/24')
        h2 = self.addHost('h2', ip='10.0.0.2/24')

        # Switches
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')

        # Links
        self.addLink(h1, s1)
        self.addLink(s1, s2)
        self.addLink(s2, h2)


class TopologyMonitor(threading.Thread):
    def __init__(self, net, interval=2):
        super().__init__(daemon=True)
        self.net = net
        self.interval = interval
        self.running = True
        self.previous_state = {}

    def log_event(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{timestamp} | {message}"
        print("\n" + line)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")

    def get_link_state(self, node1, node2):
        connections = node1.connectionsTo(node2)
        if not connections:
            return "NOT_PRESENT"

        intf1, intf2 = connections[0]
        pair = tuple(sorted((node1.name, node2.name)))

        try:
            up1 = intf1.isUp()
            up2 = intf2.isUp()
            return "UP" if up1 and up2 else "DOWN"
        except AssertionError:
            # Host/switch shell may be busy during pingall or other CLI commands
            return self.previous_state.get(pair, "DOWN")
        except Exception:
            return self.previous_state.get(pair, "DOWN")

    def display_topology(self):
        print("\n================ TOPOLOGY SNAPSHOT ================\n")

        print("Nodes:")
        for host in self.net.hosts:
            print(f"[HOST]   {host.name}  IP={host.IP()}")

        for switch in self.net.switches:
            print(f"[SWITCH] {switch.name}")

        print("\nLinks:")
        checked = set()
        all_nodes = self.net.hosts + self.net.switches

        for node in all_nodes:
            for intf in node.intfList():
                link = intf.link
                if link is None:
                    continue

                n1 = link.intf1.node.name
                n2 = link.intf2.node.name
                pair = tuple(sorted((n1, n2)))

                if pair in checked:
                    continue
                checked.add(pair)

                state = self.get_link_state(self.net.get(n1), self.net.get(n2))
                print(f"{n1} <--> {n2} : {state}")

        print("\n===================================================\n")

    def initialize_states(self):
        all_nodes = self.net.hosts + self.net.switches
        for i in range(len(all_nodes)):
            for j in range(i + 1, len(all_nodes)):
                node1 = all_nodes[i]
                node2 = all_nodes[j]
                pair = tuple(sorted((node1.name, node2.name)))
                self.previous_state[pair] = self.get_link_state(node1, node2)

    def run(self):
        self.log_event("Topology Monitor started")
        self.initialize_states()
        self.display_topology()

        all_nodes = self.net.hosts + self.net.switches

        while self.running:
            current_pairs = {}

            for i in range(len(all_nodes)):
                for j in range(i + 1, len(all_nodes)):
                    node1 = all_nodes[i]
                    node2 = all_nodes[j]
                    pair = tuple(sorted((node1.name, node2.name)))

                    try:
                        current_state = self.get_link_state(node1, node2)
                    except Exception:
                        continue

                    current_pairs[pair] = current_state
                    old_state = self.previous_state.get(pair)

                    if old_state is not None and old_state != current_state:
                        self.log_event(
                            f"LINK_CHANGE: {pair[0]} <--> {pair[1]} changed from {old_state} to {current_state}"
                        )
                        self.display_topology()

            self.previous_state.update(current_pairs)
            time.sleep(self.interval)

    def stop(self):
        self.running = False
        self.log_event("Topology Monitor stopped")


def run_topology():
    topo = SimpleTopo()

    net = Mininet(
        topo=topo,
        switch=OVSBridge,
        link=TCLink,
        controller=None,
        autoSetMacs=True
    )

    net.start()

    print("\nNetwork started successfully.")
    print("You can test using these commands inside Mininet CLI:")
    print("  pingall")
    print("  link s1 s2 down")
    print("  link s1 s2 up")
    print("  nodes")
    print("  net\n")

    monitor = TopologyMonitor(net, interval=2)
    monitor.start()

    try:
        CLI(net)
    finally:
        monitor.stop()
        monitor.join(timeout=2)
        net.stop()
        print(f"\nLogs written to {LOG_FILE}")


if __name__ == '__main__':
    setLogLevel('info')
    run_topology()