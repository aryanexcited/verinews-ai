import json
import os
import urllib.request

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.predictor import predict_baseline

app = FastAPI(
    title="VeriNews AI",
    version="1.0.0"
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

class NewsInput(BaseModel):
    text: str


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
            baseline_result = predict_baseline(text)
            return {
                "text_preview": text[:100] + "..." if len(text) > 100 else text,
                "distilbert": distilbert_result,
                "baseline": baseline_result,
                "analysis": analyze_text_signals(text, distilbert_result["prediction"]),
            }

    raise HTTPException(status_code=502, detail="Invalid response received from Space.")

@app.get("/")
def root():
    return FileResponse("app/static/index.html")

@app.post("/predict")
def predict_news(input: NewsInput):
    return remote_predict(input.text)
