from prometheus_client import Counter, Histogram

AI_RUNS = Counter("healthos_ai_runs_total", "AI runs", ["status", "team"])
AI_RUN_DURATION = Histogram("healthos_ai_run_duration_seconds", "AI run latency", ["team"])
AI_TOOL_CALLS = Counter("healthos_ai_tool_calls_total", "Agent tool calls", ["tool", "status"])
AI_MODEL_CALLS = Counter("healthos_ai_model_calls_total", "Model calls", ["model", "status"])
