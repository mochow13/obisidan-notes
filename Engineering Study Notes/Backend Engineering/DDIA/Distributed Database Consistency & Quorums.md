---
tags:
  - system-design
  - databases
  - distributed-systems
  - consistency
created: 2026-06-12
type: reference
---
## 1. Read-After-Write Consistency
**Read-after-write consistency** (or *read-your-writes*) guarantees that once a client updates a data item, any subsequent read by that same client will always return the updated value (or a newer one).

> [!INFO] The Challenge: Replication Lag
> In horizontally scalable databases, data is replicated across multiple nodes for high availability. If replication happens asynchronously, a client might write to **Node A** and immediately read from a lagging **Node B**, resulting in stale data.

### Industry-Standard Mitigations
* **Quorum Intersection:** Ensuring the read and write sets overlap mathematically.
* **Primary/Leader-Pinned Routing:** Pinning a user's reads to the primary/leader node for a short time window (e.g., 5s) immediately after they perform a write.
* **Session Tokens:** Clients carry a logical timestamp/vector clock token. Replicas block or reject the read if their local state is older than the token timestamp.
* **Consensus Leases:** Utilizing time-bound leader leases (e.g., Raft/Paxos groups) to serve strong reads instantly from the leader's memory without a full network round-trip.

---

## 2. Does Quorum Enforce Strong Consistency?
The short answer is **no**. Setting a strict mathematical quorum ($R + W > N$) is a *necessary* condition for strong consistency (Linearizability), but **not sufficient** on its own.

$$R + W > N$$

> [!WARNING] Why Simple Quorums Fail Linearizability
> In a leaderless, simple quorum system, three major anomalies can occur:
> 1. **Concurrent Reads during a Write:** Reader A might query a quorum that includes a newly updated node (returns new data), while Reader B queries a quorum hitting slower nodes a millisecond later (returns old data). Time moves forward, but data moves backward.
> 2. **Failed/Partial Writes:** If a write coordinator crashes halfway through updating a quorum, some nodes get the dirty data and others don't, leaving the system in a non-deterministic state.
> 3. **Clock Skew (Last-Write-Wins):** Wall-clock synchronization errors across physical servers can cause later updates to be accidentally overwritten by older ones.

---

## 3. Case Study: Dynamo vs. Amazon DynamoDB

There is a massive architectural difference between the decentralized theory of the 2007 Dynamo paper and the enterprise cloud service AWS built.

| Feature | The Dynamo Paper (2007) | Amazon DynamoDB (Current) |
| :--- | :--- | :--- |
| **Architecture** | **Leaderless** (Decentralized) | **Single-Leader** per partition (Multi-Paxos) |
| **Quorum Type** | "Sloppy" Quorums | Strict Consensus Quorums (2 out of 3 ACKs) |
| **Conflict Resolution**| Vector clocks / Last-Write-Wins | Strict sequence ordering via Paxos Log |
| **Consistency Level** | Eventual Consistency | Tunable (Eventual or Strong) |

### How DynamoDB Leverages Quorums safely
DynamoDB splits tables into partitions replicated across 3 nodes. It uses **Multi-Paxos** to elect a single leader for each partition. 
* **Writes:** Always route to the Paxos Leader, which commits the write only after a majority quorum (2/3 nodes) logs it to disk. This ensures extreme durability.
* **Reads:** Tuned by the client application.

> [!TIP] Optimizing DynamoDB Read Consistency
> * **Eventually Consistent Reads (Default):** Routes to a random replica. It costs 0.5 Read Capacity Units (RCUs) but risks brief replication lag.
> * **Strongly Consistent Reads (`ConsistentRead=True`):** Forces the request router to query the **Paxos Leader** directly. It costs 1.0 RCU but guarantees absolute Linearizability.