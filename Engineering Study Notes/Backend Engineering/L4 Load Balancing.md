- **Source:** [Arpit Bhayani - L4 Load Balancers](http://www.youtube.com/watch?v=RcarDmgWezY)
- **Tags:** #networking #infrastructure #load-balancing #system-design #L4

---

## L4 Proxy Mode - Connection Termination

In Proxy mode, the Load Balancer (LB) acts as a "middleman" that participates actively in the network conversation.

### How it Works - The Two-Connection Model

* **Termination:** The client establishes a TCP connection with the LB. The handshake (`SYN, SYN-ACK, ACK`) ends at the LB.
* **Re-establishment:** The LB then opens a **second, separate** TCP connection to the chosen backend server.
* **Data Flow:** The LB receives data from Connection A and forwards it onto Connection B.
### Key Characteristics

* **Smarter Routing:** Because the LB manages the connection to the backend, it can track **active connection counts**, **latencies**, and **server health** to make better decisions (e.g., Least Connections routing).
* **Observability:** Provides deep metrics on connection duration, resets, and retries.
* **Overhead:** higher CPU/Memory usage because the LB has to maintain the state for two connections for every single client.
* **Examples:** HAProxy, NGINX (Stream module), Envoy.

---

## 2. L4 Pass-through (NAT Mode)

The LB acts as a high-speed traffic controller that redirects packets without "breaking" the initial TCP handshake.

### How it Works (The "Envelope" Swap)

* **NAT Rewrite:** The LB performs **Network Address Translation (NAT)**. It replaces the **Destination IP** (the LB's VIP) with the IP of a backend server.
* **Single Connection:** There is only one end-to-end TCP connection. The handshake technically happens between the client and the backend server, with the LB just "passing the mail."
* **Bidirectional:** Both requests and responses **must** pass through the LB so it can swap the IPs back (Source IP masking) to prevent the client from rejecting "unrecognised" packets.
### Key Characteristics

* **High Performance:** Much faster than Proxy mode because it doesn't have to manage connection states or buffers.
* **Examples:** AWS Network Load Balancer (NLB), Linux `iptables`.

---
## 3. Direct Server Return (DSR)

An advanced optimisation where the response traffic bypasses the Load Balancer entirely.

### How it Works (The Layer 2 Trick)

* **MAC Rewrite:** The LB keeps the **Destination IP** as its own VIP but changes the **Destination MAC Address** to the backend server's MAC.
* **Loopback Identity:** The backend server has a "hidden" **Loopback Interface** configured with the LB's VIP. It accepts the packet because it thinks it "is" the target.
* **Direct Path:** The server generates a response and sends it **directly to the client** via the internet gateway, using the LB's VIP as the Source IP.

---
## 4. Summary Comparison Table

| Feature | Proxy Mode | Pass-through (NAT) | Direct Server Return (DSR) |
| :--- | :--- | :--- | :--- |
| **TCP Connections** | Two (Client-LB, LB-Server) | One (End-to-End) | One (End-to-End) |
| **Response Path** | Through LB | Through LB | **Direct to Client** |
| **Routing Logic** | Smart (Least Conn, Latency) | Simple (Round Robin, Hash) | Simple (MAC-based) |
| **LB Bottleneck** | High (State management) | Moderate (Bandwidth) | **Low** (Request only) |
| **Configuration** | Easy | Moderate | Difficult (Server-side config) |

---

## 5. Decision Matrix
* **Need Smart Routing / Health Awareness?** → Use **Proxy Mode**.
* **Need High Throughput / Standard Setup?** → Use **Pass-through (NAT)**.
* **Handling Massive Outgoing Data (e.g., Video)?** → Use **DSR**.