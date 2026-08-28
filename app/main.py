import json
import os
import socket
import urllib.error
import urllib.request
import logging
import time
import uuid

from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from typing import Literal
from pydantic import BaseModel, Field

from app.predictor import predict_baseline
from app.verifier import extract_claims, build_claim_results, verify_claim 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("verinews")

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_PATH = STATIC_DIR / "index.html"

app = FastAPI(
    title="VeriNews AI",
    version="1.0.0"
)

@app.middleware("http")
async def request_logging_middleware(request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start_time = time.perf_counter()

    response = None

    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    finally:
        duration = time.perf_counter() - start_time

        logger.info(
            "request_id=%s method=%s path=%s status=%s duration=%.3fs",
            request_id,
            request.method,
            request.url.path,
            getattr(response, "status_code", "error"),
            duration,
        )

class HealthResponse(BaseModel):
    status: str
    service: str
    baseline_model: str
    prediction_provider: str

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns the current API health status."
)
async def health_check():
    return {
        "status": "healthy",
        "service": "VeriNews AI",
        "baseline_model": "loaded",
        "prediction_provider": "configured"
    }

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

class NewsInput(BaseModel):
    text: str = Field(
        ...,
        min_length=3,
        max_length=10000,
        description="News article or headline to analyze."
    )

SPACE_API_URL = os.getenv(
    "SPACE_API_URL",
    "https://ryancoder-fake-news-detector-api.hf.space",
)


def analyze_text_signals(text: str, prediction: str) -> dict:
    lowered = text.lower()
    signals = []

    sensational_phrases = [
        "shocking",
        "breaking",
        "you won't believe",
        "secret",
        "miracle",
        "exposed",
        "must read",
    ]
    vague_attribution_phrases = [
        "experts say",
        "people are saying",
        "sources say",
        "many believe",
        "it is being reported",
    ]

    if any(phrase in lowered for phrase in sensational_phrases):
        signals.append("Uses sensational or clickbait-style wording")
    if any(phrase in lowered for phrase in vague_attribution_phrases):
        signals.append("Relies on vague attribution instead of clearly named sources")
    if text.count("!") >= 2 or text.count("?") >= 3:
        signals.append("Uses unusually strong punctuation for emphasis")

    uppercase_words = [
        word for word in text.split()
        if len(word) > 3 and word.isupper()
    ]
    if len(uppercase_words) >= 3:
        signals.append("Contains several all-caps words that increase emotional tone")

    if "http://" not in lowered and "https://" not in lowered and "according to" not in lowered:
        signals.append("Does not clearly point to a source or supporting reference")

    if not signals:
        signals.append("Shows fewer obvious stylistic warning signs in the text alone")

    if prediction == "FAKE":
        why_flagged = (
            "The model flagged patterns often associated with misleading content, "
            "especially around tone, sourcing, or exaggerated framing."
        )
    else:
        why_flagged = (
            "The model found fewer high-risk language patterns, though this is still "
            "a style-based prediction rather than a verified fact-check."
        )

    return {
        "risk_signals": signals[:4],
        "why_flagged": why_flagged,
        "fact_check_note": (
            "This is an automated prediction. Important claims should still be verified "
            "with trusted reporting or primary sources."
        ),
    }


def remote_predict(text: str):
    request_body = json.dumps({"data": [text]}).encode("utf-8")
    start_request = urllib.request.Request(
        f"{SPACE_API_URL}/gradio_api/call/predict",
        data=request_body,
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(start_request, timeout=60) as response:
        start_payload = json.loads(response.read().decode("utf-8"))

    event_id = start_payload.get("event_id")
    if not event_id:
        raise HTTPException(status_code=502, detail="Space did not return an event id.")

    with urllib.request.urlopen(
        f"{SPACE_API_URL}/gradio_api/call/predict/{event_id}",
        timeout=120,
    ) as response:
        stream_text = response.read().decode("utf-8")

    for chunk in stream_text.split("\n\n"):
        lines = [line for line in chunk.splitlines() if line.strip()]
        if len(lines) >= 2 and lines[0].strip() == "event: complete":
            data_line = next((line for line in lines if line.startswith("data: ")), None)
            if not data_line:
                break
            payload = json.loads(data_line[6:])
            if not payload:
                break
            distilbert_result = payload[0]

            confidence = distilbert_result.get("confidence")

            if isinstance(confidence, str):
                confidence = confidence.replace("%", "").strip()

            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = None

            distilbert_result["confidence"] = confidence

            baseline_result = predict_baseline(text)
            claims = extract_claims(text)

            return {
                "text_preview": text[:100] + "..." if len(text) > 100 else text,
                "distilbert": distilbert_result,
                "baseline": baseline_result,
                "analysis": analyze_text_signals(
                    text,
                    distilbert_result["prediction"],
                ),
                "claims": claims,
                "verification": [
                    verify_claim(claim)
                    for claim in claims
                ],
            }

    raise HTTPException(status_code=502, detail="Invalid response received from Space.")

@app.get("/")
def root():
    return FileResponse(INDEX_PATH)

class ModelPrediction(BaseModel):
    prediction: Literal["FAKE", "REAL"]
    confidence: float | None = Field(
        default=None,
        ge=0,
        le=100
    )
class AnalysisResult(BaseModel):
    risk_signals: list[str]
    why_flagged: str
    fact_check_note: str


class PredictionResponse(BaseModel):
    text_preview: str
    distilbert: ModelPrediction
    baseline: ModelPrediction
    analysis: AnalysisResult

class ClaimResult(BaseModel):
    claim: str
    status: str
    evidence: list[dict]


class EvidenceItem(BaseModel):
    title: str
    description: str
    url: str
    source: str
    published_at: str
    relevance_score: float
    classification: Literal[
        "SUPPORTS",
        "CONTRADICTS",
        "RELATED",
        "UNVERIFIED",
    ]


class VerificationResult(BaseModel):
    claim: str
    status: Literal[
        "SUPPORTED",
        "CONTRADICTED",
        "RELATED",
        "UNVERIFIED",
    ]
    evidence: list[EvidenceItem]


class PredictionResponse(BaseModel):
    text_preview: str
    distilbert: ModelPrediction
    baseline: ModelPrediction
    analysis: AnalysisResult
    claims: list[str]
    verification: list[VerificationResult] 

@app.post("/predict", response_model=PredictionResponse,summary="Analyze news credibility", description="Analyzes submitted news text using DistilBERT and a TF-IDF baseline.")
async def predict_news(request: Request, input: NewsInput):
    try:
        return remote_predict(input.text)
    except HTTPException:
        raise
    except urllib.error.HTTPError as error:
        status_code = 503 if error.code == 429 or error.code >= 500 else 502
        raise HTTPException(
            status_code=status_code,
            detail=f"Prediction provider returned HTTP {error.code}. Please try again shortly.",
        ) from error
    except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
        raise HTTPException(
            status_code=503,
            detail="Prediction provider is temporarily unavailable. Please try again shortly.",
        ) from error
    except Exception as exc:
        logger.exception("Prediction failed")
        raise HTTPException(
            status_code=500,
            detail=f"Prediction service error: {type(exc).__name__}: {exc}",
        ) from exc