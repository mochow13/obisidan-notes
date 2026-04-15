Based on: [Database Connection Pool Sizing - Demystified!](https://youtu.be/Cp-aFYHLiCw)

Cconnection pool size involves balancing the minimum requirements for your workload with the maximum capacity your hardware can handle.

## Determining Minimum Pool Size (Little's Law)

To find the minimum number of connections needed to sustain your current throughput, you can use **Little's Law**.

**Formula:** $L = \lambda \times W$
* **$L$**: Minimum connections (Work in Progress).
* **$\lambda$**: Throughput (Average transactions per second).
* **$W$**: Service time (Average query execution time).

**Example:** If your application handles **50 transactions per second** and each query takes **100ms (0.1s)**, you need at least **5 connections** to keep up.

## Determining Maximum Pool Size (The HikariCP Formula)

The video highlights a widely accepted formula from the HikariCP documentation to determine the upper limit of your pool size:

**Formula:** `Pool Size = (CPU Core Count * 2) + Effective Spindle Count`

* **CPU Core Count**: The number of cores available to the database server. Modern CPUs can often handle 2 threads per core.
* **Effective Spindle Count**: This relates to disk performance. For modern **SSDs**, this value is typically **1**. For traditional hard drives (HDDs), it may be higher.

**Example:** For a **4-core server** with an SSD, the calculation would be: $(4 \times 2) + 1 = 9$ connections.

## Key Considerations for Sizing

* **Kingman’s Law & Utilization:** You should aim to keep pool utilization below **80%**. Once you exceed this "danger zone," waiting times for a connection increase exponentially, leading to timeouts and performance degradation.
* **Context Switching:** Having a pool that is too large (e.g., hundreds of connections for a small CPU) is often more harmful than a pool that is too small. It forces the CPU to waste time "context switching" between processes rather than executing queries.
* **Workload Separation:** If you have different types of tasks (e.g., short web requests vs. long-running batch jobs), it is often better to use separate connection pools for each to prevent batch jobs from starving short requests of resources.

### Real-Life Example

A finance system was using 8 JVMs, each configured with 80 connections, totaling **640 connections** to a 104-core server.
* **Calculated Max:** $(104 \text{ cores} \times 2) + 8 \text{ spindles} = \mathbf{216 \text{ connections}}$.
* **The Result:** The pool was nearly 3x larger than the hardware could efficiently handle, causing massive overhead during initialization and operation.