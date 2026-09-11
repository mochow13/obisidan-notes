Based on: https://www.youtube.com/watch?v=2Obf2LqEvyk
## What impacts latency of an application?
- GC pauses
- GC work done by application threads!
- Allocation stalls—when GC allocates faster than freeing up memory
- Large allocations
## What impacts footprint?
- Additional native memory required by the GC
- CPU usage doing GC work
## What impacts throughput?
- Concurrent GC work
- GC pauses
- Read and write barriers (verification code GC needs to do its work)
## Tradeoffs
- Stop the world GC work good for throughput but worse for latency
	- GC work is done during pauses
	- Application threads run full otherwise
	- Impacts latency

![[Screenshot 2026-01-20 at 21.34.53.png]]

- Concurrent GC is good for lower latency
	- GC threads run with application threads concurrently
	- GC pauses are short—synchronising between application threads and GC threads
	- Impacts throughputs

![[Screenshot 2026-01-20 at 21.36.53.png]]

## G1GC
- Strike a balance between latency, footprint, throughput
- Part of the work is concurrently
- Can do mixed collections—instead of a big pause, collect garbage over a set of pauses
- G1 can be tuned to have shorter GC pauses through a config

## ZGC
- Suitable for low latency
- Can be used both for small and large heaps
	- Common misconception is that it's only for large heaps

## Configs to tune
- `-XX:+UseLargePages`, `-XX:+UseTransparentHugePages`
- `-XX:+AlwaysPreTouch`