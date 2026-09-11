Based on: [Mastering LLM Inference Optimization From Theory to Cost Effective Deployment: Mark Moyou](https://www.youtube.com/watch?v=9tvJ_GYJA-o)

Simple mental model to calculate memory on GPU: number of parameters x 2 = memory in GPU for FP16 in GB

Example: Llama 8b model requires 8 x 2 = 16GB in GPU memory for FP16 precision

### Metrics to monitor
- TTFT - time to first token
	- Measures the performance of prefill and KV cache efficiency
- Inter-token latency
	- Measures the consistent performance of the system
	- If the output sequence length is longer, there should be minimal variation in inter-token latencies
- Completion time (time from prompt to response)
	- Measures overall performance of deployment and generation phase