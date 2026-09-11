Based on: [How Uber Conquered Database Overload: The Journey from Static Rate-Limiting to Intelligent Load Management](https://www.uber.com/us/en/blog/from-static-rate-limiting-to-intelligent-load-management/?uclick_id=47db5de8-06b2-4027-9149-1791355cb2e7)

The article explains how Uber evolved its database protection strategy from rigid, static quotas to a dynamic, "intelligent load manager" integrated directly into its storage layer.
The core narrative follows their journey in solving database overloads for Docstore and Schemaless (their in-house distributed databases) through several key innovations.

We have some key learnings from the article:
## Monitor Concurrency, Not Just Throughput

One of the biggest shifts was moving away from **QPS (Queries Per Second)** as a metric for load. 

* QPS is a "blind" metric because it doesn't account for how much work each query actually does. 
* By using **Little’s Law** ($L = \lambda W$), Uber focused on **Concurrency** (the number of requests currently in flight). This directly reflects how many system resources (threads, memory, connections) are being held, making it a much more accurate signal for when a system is hitting its physical limits.

## "Fail Fast" is a Mercy for the System

Uber found that holding onto requests in a queue during an overload is actually more damaging than rejecting them immediately.

* Large queues lead to "bufferbloat," where requests sit in memory, consume goroutines, and increase the likelihood of **OOM (Out of Memory)** crashes.
* Rejecting a request at the "front door" (the Scorecard) costs almost nothing. It clears the path for healthy requests and prevents a backlog that would eventually time out anyway.

### Adaptive LIFO vs. FIFO Traps

A major learning from the CoDel implementation was that **FIFO (First-In, First-Out)** queuing is counterproductive during an overload.

- In a saturated system, requests at the front of the line are often already "stale" because the client has likely timed out or retried.
- CoDel introduced **Adaptive LIFO**, which switches to processing the **newest** requests first during pressure. This "fails fast" on old work and gives fresh requests a higher probability of success, preventing the system from wasting resources on requests that are already dead to the user.

## Prioritization is the Ultimate Safety Net

In a massive multi tenant system, you cannot treat a "Data Cleanup" job the same as a "Ride Request."

* Without priority awareness, a surge in low-priority background tasks can accidentally take down the entire business.
* By implementing the **Cinnamon** tiering model (**T0–T5**), Uber ensured that the most critical business functions have a "VIP lane." During an overload, the system systematically "sacrifices" the lower tiers to keep the core business alive.

## Control Theory Prevents "Thundering Herds"

Early shedding attempts used binary logic (if load > X, drop all). This caused the "Thundering Herd" problem, where traffic would oscillate wildly between 0% and 100%.

* Abrupt shedding leads to instability.
* Using a **PID Controller** allows for "smooth regulation." It’s the difference between a light switch and a dimmer switch. The system reacts proportionally to the *speed* and *size* of the spike, leading to a much faster and smoother recovery.
## PID Controller

Uber uses the PID loop to calculate a **rejection ratio** $u(t)$ based on the **"error"** $e(t)$, which is the difference between current latency/load and the desired target.

* **Proportional (P): Reacts to the Present.** If the database is currently 10% over its latency target, it sheds a proportional amount of traffic.
* **Integral (I): Reacts to the Past.** It looks at the accumulated error over time. This ensures that if a system stays "slightly" overloaded for a long duration, the controller gradually increases the pressure to fix it.
* **Derivative (D): Reacts to the Future.** It measures the **rate of change**. If traffic is spiking vertically, the D component detects the "velocity" and begins shedding traffic *before* the system actually hits the breaking point.
## Move Logic to the "Point of Saturation"

Initially, Uber tried to manage load in the stateless Query Engine (the entry point).

* The routing layer doesn't know the real-time health of the thousands of underlying database partitions.
* Load management is most effective when it lives as close to the **stateful storage engine** as possible. This ensures the shedding decisions are based on actual hardware signals (disk I/O, memory, commit lag) rather than guesses from a remote proxy.

## The "Bring Your Own Signal" (BYOS) Philosophy

Overload isn't always caused by a local CPU spike; sometimes it's caused by a downstream dependency or a lagging database follower.

* Local health checks aren't enough for distributed systems.
* By building a pluggable architecture, Uber allows the load manager to ingest any signal—whether it's local memory or remote "commit lag"—and feed it into the same PID loop for a unified response.
