---
title: Modern Hardware Numbers
aliases:
  - System Design Hardware Cheat Sheet
tags:
  - system-design
  - interview-prep
  - hardware
created: 2026-09-12
---
A practical reference for system design interviews*

> [!abstract] The five numbers to remember
> **Cache ≈ 1 ns · RAM ≈ 100 ns · Local SSD ≈ 100 μs · Nearby service ≈ 1 ms · Distant region ≈ 100 ms**
>
> Memorize orders of magnitude, state your assumptions, and use them to identify the bottleneck.

> [!info] How to read this note
> These are rounded interview estimates, not guaranteed benchmarks. Performance depends on hardware, workload, concurrency, and load. Product examples are reference points rather than a survey of the newest hardware.

## Latency ladder

| Operation | Useful range | Memorize |
| :--- | :--- | ---: |
| CPU cycle at 2–4 GHz | 0.25–0.5 ns | **0.3 ns** |
| L1 cache hit | 1–2 ns | **1 ns** |
| L2 cache hit | 3–10 ns | **5 ns** |
| L3 cache hit | 10–50 ns | **20 ns** |
| Local DRAM access | 70–150 ns | **100 ns** |
| Small random read from local NVMe SSD | 50–200 μs | **100 μs** |
| Small I/O to cloud block storage | 0.3–5 ms, tier dependent | **1 ms** |
| Random HDD read, including seek | 5–15 ms | **10 ms** |
| Small same-datacenter RPC, established connection | 0.1–1 ms | **0.5 ms** |
| Cross-availability-zone round trip | Roughly 0.5–2 ms | **1 ms** |
| Cross-region round trip | 20–200+ ms, distance dependent | **100 ms** |

> [!tip] Think in ratios
> With these defaults, a local SSD read takes about **1,000×** as long as a RAM access. A 100 ms cross-region round trip takes about **100×** as long as a 1 ms nearby call.

Networking entries are planning assumptions. Service execution, connection setup, and queueing add time. As a concrete storage reference, AWS specifies average latency below **500 μs for 16 KiB I/O** on io2 Block Express. [AWS documentation](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-optimization.html)

## Throughput and IOPS

| Resource | Interview assumption | Scope and caveat |
| :--- | :--- | :--- |
| RAM bandwidth | **100 GB/s per server**, explicitly assumed | Aggregate across cores and memory channels; a small VM gets much less |
| Local NVMe sequential reads | **3–14 GB/s per drive** for PCIe 4/5 hardware | Sustained writes can be substantially slower |
| Local NVMe random reads | **100K–1M+ IOPS** | Requires sufficient concurrency; specify block size and queue depth |
| HDD sequential reads | **150–300 MB/s per drive** | Large sequential scans remain viable |
| HDD random reads | **100–200 IOPS per drive** | Random access is the major limitation |
| Server networking | **10–100 Gbps**, explicitly chosen | VM size, burst limits, and traffic path matter |

> [!example]- Modern hardware reference points
> These are configuration-specific ceilings, not default application throughput.
>
> - **Memory:** AMD lists **614 GB/s theoretical bandwidth per socket** for the EPYC 9555. [Specifications](https://www.amd.com/en/products/processors/server/epyc/9005-series/amd-epyc-9555.html)
> - **Storage:** Micron’s 9550 advertises **14 GB/s sequential reads** and **3.3 million random-read IOPS**. [Specifications](https://www.micron.com/products/storage/ssd/data-center-ssd/9550-ssd)
> - **Network:** Some large EC2 instances advertise **hundreds of Gbps** of networking. [Specifications](https://aws.amazon.com/ec2/instance-types/general-purpose/)

## What a modern server holds

Modern hardware breaks the memory and disk assumptions from older textbooks, often by orders of magnitude. Know the ceilings so you don't reach for a distributed design before a single large box is exhausted.

| Resource | Commodity server | High end | Memorize |
| :--- | :--- | :--- | ---: |
| vCPUs / cores | 8–64 | 128+ | **32 cores** |
| RAM | 64–512 GB | 4–24 TB | **512 GB** |
| Local SSD | 1–8 TB | up to 60 TB | **~10 TB** |
| Network | 10 Gbps standard | 100+ Gbps | **10 Gbps** |

> [!example]- Concrete instance reference points
> These are real ceilings, not defaults you should assume for every box.
>
> - **Balanced cloud:** AWS `m6i.32xlarge` offers **128 vCPUs and 512 GiB RAM**. [Specifications](https://aws.amazon.com/ec2/instance-types/m6i/)
> - **Memory-optimized:** AWS `x1e.32xlarge` reaches **4 TB RAM**; `u-24tb1.metal` reaches **24 TB RAM**. [Specifications](https://aws.amazon.com/ec2/instance-types/high-memory/)
> - **Dedicated / bare metal:** Hetzner `AX162-R` packs **up to 1.152 TB RAM and 48 cores** for a fraction of cloud cost. [Specifications](https://www.hetzner.com/dedicated-rootserver/ax162-r/)

## Per-component capacity on modern hardware

A single well-tuned node goes much further than conventional wisdom suggests. Shard for operational reasons (backup windows, blast radius) before raw performance forces it.

| Component | Throughput | Latency | Capacity ceiling |
| :--- | :--- | :--- | :--- |
| Cache (e.g. Redis) | **100K+ ops/s** per instance | single-digit ms in region | **up to ~1 TB** dataset |
| SQL DB (Postgres/MySQL) | **10–20K writes/s** per primary, up to ~20K connections | 1–5 ms cached, 5–30 ms disk | **up to ~64 TiB** per instance |
| Message queue (e.g. Kafka) | **up to ~1M msgs/s** per broker | 1–5 ms end-to-end in region | **up to ~50 TB** per broker |
| App server | **100K+ concurrent connections** | CPU-bound, not connection-bound | 8–64 cores, 64 GB–2 TB RAM |

> [!tip] Design implication
> With these numbers, a single primary database plus a couple of read replicas handles more load than whole clusters did a few years ago. Start simple and add distribution only when a specific limit forces it. CPU, not memory or connection count, is usually the first wall on app servers.

## Conversions to know cold

| Conversion | Result |
| :--- | ---: |
| 1 μs | **1,000 ns** |
| 1 ms | **1,000 μs** |
| 1 byte | **8 bits** |
| 1 Gbps | **125 MB/s** before overhead |
| 10 Gbps | **1.25 GB/s** before overhead |
| 100 Gbps | **12.5 GB/s** before overhead |
| 1 million requests/day | **≈12 requests/s average** |
| 1 billion requests/day | **≈12,000 requests/s average** |
| 1 KB × 1 million records | **≈1 GB** raw data |
| 1 KB × 1 billion records | **≈1 TB** raw data |

Use decimal units for quick arithmetic. Distinguish **GB** from **GiB** when precision matters. Daily averages do not account for traffic peaks.

## Put the numbers to work

### 01 · Network capacity

$$
\text{Bandwidth} = \text{requests/s} \times \text{bytes/response}
$$

**100K responses/s × 10 KB = 1 GB/s ≈ 8 Gbps**, before protocol overhead.

> [!success] Design implication
> A 10 Gbps link leaves little headroom. Consider a larger link, more serving nodes, smaller responses, or caching closer to users.

### 02 · CPU capacity

$$
\text{Requests/s per core} \approx \frac{\text{target utilization}}{\text{CPU seconds per request}}
$$

At **1 ms of CPU time per request**, one core supports a theoretical maximum of **1,000 requests/s**. With a chosen **60% utilization** target, budget **600 requests/s/core**.

> [!note] CPU time versus response time
> Use actual CPU work in this calculation. Time spent waiting on a network or disk does not necessarily occupy a core.

### 03 · In-flight requests

$$
\text{Average in-flight requests} = \text{throughput} \times \text{average latency}
$$

**10K requests/s × 20 ms = 200 requests in flight.**

This is Little’s Law for a stable system. Use it to reason about concurrency and connection pools; in-flight requests need not map one-to-one to threads.

### 04 · Storage capacity

$$
\text{Replicated data size} = \text{logical data size} \times \text{replica count}
$$

**1 TB of logical data × 3 full replicas = 3 TB**, before indexes, logs, metadata, and free space.

## Three distinctions that prevent mistakes

> [!warning] Latency is not inverse peak IOPS
> A drive with **100 μs reads** handles about **10K sequentially issued reads/s**. Many concurrent requests can produce much higher aggregate IOPS. Always specify access pattern, I/O size, and concurrency.

> [!warning] Device latency is not database latency
> Queries add CPU work, network hops, locking, logging, and sometimes replication. A write acknowledgment can also have different durability guarantees.

> [!warning] Average is not p99
> Queueing and contention can dominate near saturation. Size for peak traffic, tail latency, and surviving a failure.

## Interview opening

> [!quote] State a concrete machine assumption
> “I’ll assume this machine has 32 cores, 128 GB RAM, and 10 Gbps networking, then check which resource limits the workload.”

Explicit assumptions and sound arithmetic matter more than memorizing a particular server SKU.

## Quick self-check

- [ ] Recall the five-number latency ladder.
- [ ] Convert Gbps to GB/s without confusing bits and bytes.
- [ ] Convert daily requests to average requests per second.
- [ ] Estimate network, CPU, concurrency, and storage needs.
- [ ] Explain why peak IOPS is not the inverse of single-request latency.
- [ ] Account for peaks, p99 latency, replication, and failure headroom.
