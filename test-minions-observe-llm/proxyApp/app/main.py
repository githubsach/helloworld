from fastapi import FastAPI, Request
from pydantic import BaseModel
from random import choice
import time
import httpx
import os
import openlit

# === OpenTelemetry Setup ===
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_client import start_http_server, Counter, Histogram



# === Load config from environment ===
SERVICE_NAME_CONFIG = os.getenv("SERVICE_NAME", "vllm-proxy-default")

# Parse VLLM_ENDPOINTS from env like: v1=http://vllm1:8001/generate,v2=http://vllm2:8002/generate
raw_endpoints = os.getenv("VLLM_ENDPOINTS", "")
VLLM_ENDPOINTS = {}
for item in raw_endpoints.split(","):
    if "=" in item:
        version, url = item.split("=", 1)
        VLLM_ENDPOINTS[version.strip()] = url.strip()

# === Prometheus Metrics ===
request_count = Counter("vllm_requests_total", "Total prompts processed", ["version"])
request_latency = Histogram("vllm_request_latency_seconds", "LLM response time", ["version"])

# === FastAPI + OpenTelemetry Setup ===
app = FastAPI()

# === OpenTelemetry Setup ===
trace.set_tracer_provider(
    TracerProvider(resource=Resource.create({SERVICE_NAME: SERVICE_NAME_CONFIG}))
)
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(ConsoleSpanExporter())
)
tracer = trace.get_tracer(__name__)

FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()
LoggingInstrumentor().instrument()

# === OpenLIT Setup ===
openlit.init()

# === Request schema ===
class PromptRequest(BaseModel):
    prompt: str
    version: str | None = None  # optional override

# === /generate endpoint ===
@app.post("/generate")
async def generate_text(request: PromptRequest):
    version = request.version or choice(list(VLLM_ENDPOINTS.keys()))  # A/B random split
    endpoint = VLLM_ENDPOINTS[version]

    with tracer.start_as_current_span("generate_text") as span:
        span.set_attribute("llm.version", version)
        span.set_attribute("llm.endpoint", endpoint)

        start_time = time.time()

        async with httpx.AsyncClient() as client:
            resp = await client.post(endpoint, json={"prompt": request.prompt})
            result = resp.json()

        duration = time.time() - start_time
        request_count.labels(version=version).inc()
        request_latency.labels(version=version).observe(duration)

        return {
            "version": version,
            "response": result.get("text"),
            "latency_seconds": round(duration, 3)
        }

# Start Prometheus metrics server on a side port
start_http_server(9100)

# Run with: uvicorn main:app --reload --port 8000
