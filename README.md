# VeriNews AI

An end-to-end NLP project that classifies news articles as REAL or FAKE. The public web app uses a lightweight FastAPI frontend on Render and calls a Hugging Face Space for DistilBERT inference.

## Tech Stack
Python · FastAPI · Hugging Face Spaces · Gradio · Transformers

## Results

| Model | Accuracy |
|---|---|
| TF-IDF + Logistic Regression | 90.1% |
| DistilBERT (fine-tuned) | 97.4% |

## Project Structure
fake-news-detector/
├── app/
│   ├── main.py        # FastAPI app + remote Space inference call
│   └── predictor.py   # Local model inference module (kept for offline use)
├── app/static/        # Frontend UI
├── scripts/           # Helper scripts
├── Dockerfile         # Optional container setup
└── requirements.txt

## Run Locally

### Windows PowerShell

```powershell
git clone https://github.com/aryanexcited/fake-news-detector.git
cd fake-news-detector
pip install -r requirements.txt
$env:SPACE_API_URL="https://ryancoder-fake-news-detector-api.hf.space"
uvicorn app.main:app --reload
```

### Linux / macOS

```bash
git clone https://github.com/aryanexcited/fake-news-detector.git
cd fake-news-detector
pip install -r requirements.txt
export SPACE_API_URL=https://ryancoder-fake-news-detector-api.hf.space
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/ for the frontend or http://127.0.0.1:8000/docs for the API docs.

## API Endpoints

- `GET /` — Frontend page
- `POST /predict` — Takes news text, forwards it to the Hugging Face Space, and returns prediction + confidence

## Free Render Deployment

This project is set up to use a free deployment flow where:
- Render hosts the lightweight FastAPI frontend
- a Hugging Face Space hosts the DistilBERT model
- the Render app calls the Space over HTTP for predictions

### 1. Hugging Face services used

- Model repo: `RYancoder/fake-news-detector-models`
- Inference Space: `https://ryancoder-fake-news-detector-api.hf.space`

The model artifacts live in the Hugging Face model repository, and the Space loads them for inference.

Model repo layout:

```text
distilbert_model/config.json
distilbert_model/model.safetensors
distilbert_model/tokenizer.json
distilbert_model/tokenizer_config.json
baseline_model.pkl
vectorizer.pkl
```

### 2. Create the Render web service

- Connect this GitHub repo to Render
- Create a `Web Service`
- Use these settings:

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### 3. Add Render environment variables

Set this environment variable in Render:

```text
SPACE_API_URL=https://ryancoder-fake-news-detector-api.hf.space
```

### 4. Important note about the free plan

The Hugging Face Space may sleep when idle on the free tier, so the first prediction after inactivity can be slower due to cold start. This is normal for a zero-cost demo setup.

## Dataset
[WELFake / fake_or_real_news](https://github.com/lutzhamel/fake-news) — 6,335 news articles, balanced classes.
