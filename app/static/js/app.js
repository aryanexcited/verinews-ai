const elements = {
    textarea: document.getElementById("newsInput"),
    detectBtn: document.getElementById("detectBtn"),
    clearBtn: document.getElementById("clearBtn"),
    loading: document.getElementById("loading"),
    error: document.getElementById("error"),
    result: document.getElementById("result"),

    verdict: document.getElementById("verdict"),
    confidence: document.getElementById("confidence"),

    bertVerdict: document.getElementById("bertVerdict"),
    baselineVerdict: document.getElementById("baselineVerdict"),

    whyFlagged: document.getElementById("whyFlagged"),
    riskSignals: document.getElementById("riskSignals"),
    factCheckNote: document.getElementById("factCheckNote"),

    verificationResults: document.getElementById("verificationResults"),

    wordCount: document.getElementById("wordCount"),
    charCount: document.getElementById("charCount"),
    readingTime: document.getElementById("readingTime")
};

const loadingSteps = [
    "Preparing analysis...",
    "Preprocessing article...",
    "Running DistilBERT model...",
    "Comparing with Classical ML...",
    "Generating credibility report..."
];

let loadingInterval;

// ---------------------------
// Live statistics
// ---------------------------

elements.textarea.addEventListener("input", updateStats);

function updateStats() {
    const text = elements.textarea.value.trim();

    const words = text ? text.split(/\s+/).length : 0;
    const chars = text.length;

    let readTime;

    if (words === 0) {
        readTime = "0 sec";
    } else if (words < 200) {
        readTime = `${Math.ceil(words / 200 * 60)} sec`;
    } else {
        readTime = `${Math.ceil(words / 200)} min`;
    }

    elements.wordCount.textContent = `${words} Words`;
    elements.charCount.textContent = `${chars} Characters`;
    elements.readingTime.textContent = readTime;
}

// ---------------------------
// Loading
// ---------------------------

function startLoading() {
    let step = 0;

    elements.loading.style.display = "flex";

    document.getElementById("loadingText").textContent =
        loadingSteps[0];

    loadingInterval = setInterval(() => {
        step++;

        if (step < loadingSteps.length) {
            document.getElementById("loadingText").textContent =
                loadingSteps[step];
        }
    }, 700);
}

function stopLoading() {
    clearInterval(loadingInterval);
    elements.loading.style.display = "none";
}

// ---------------------------
// Clear button
// ---------------------------

elements.clearBtn.addEventListener("click", () => {
    elements.textarea.value = "";

    updateStats();

    elements.result.style.display = "none";
    elements.error.style.display = "none";
});

// ---------------------------
// Detect
// ---------------------------

async function detect() {
    const text = elements.textarea.value.trim();

    if (!text) {
        alert("Please paste a news article first.");
        return;
    }

    const startTime = performance.now();

    elements.detectBtn.disabled = true;
    elements.detectBtn.textContent = "Analyzing...";

    startLoading();

    document.body.style.cursor = "wait";
    elements.error.style.display = "none";
    elements.result.style.display = "none";

    try {
        const response = await fetch("/predict", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                text: text
            })
        });

        if (!response.ok) {
            let message = `Request failed (${response.status}).`;

            try {
                const errorData = await response.json();
                message = errorData.detail || message;
            } catch (_) {
                // Keep the status-based message when the response is not JSON.
            }

            throw new Error(message);
        }

        const data = await response.json();

        const elapsed = performance.now() - startTime;

        document.getElementById("analysisTime").textContent =
            `Completed in ${(elapsed / 1000).toFixed(2)}s`;

        document.getElementById("analysisDate").textContent =
            new Date().toLocaleString("en-IN", {
                dateStyle: "medium",
                timeStyle: "short"
            });

        renderPrediction(data);
    }

    catch (err) {
        console.error(err);

        elements.error.textContent =
            `Unable to analyze the article. ${err.message}`;

        elements.error.style.display = "block";
    }

    finally {
        elements.detectBtn.disabled = false;
        elements.detectBtn.textContent = "Analyze News";

        stopLoading();

        document.body.style.cursor = "default";
    }
}

// ---------------------------
// Verification
// ---------------------------

function getSourceName(source) {
    if (source.source && source.source.trim()) {
        return source.source;
    }

    if (source.url) {
        try {
            const hostname = new URL(source.url).hostname
                .replace(/^www\./, "");

            const knownSources = {
                "bbc.com": "BBC",
                "nasa.gov": "NASA",
                "mnspacegrant.org": "Minnesota Space Grant Consortium"
            };

            return knownSources[hostname] || hostname;
        } catch (_) {
            // Fall through to generic source name.
        }
    }

    return "Unknown source";
}

function renderVerification(verification) {
    elements.verificationResults.innerHTML = "";

    if (!Array.isArray(verification)) {
        console.error("Expected verification array, got:", verification);
        return;
    }

    verification.forEach(item => {
        const card = document.createElement("div");
        card.className = "verification-card";

        const status = item.status || "UNVERIFIED";

        const evidence = Array.isArray(item.evidence)
            ? item.evidence
            : [];

        let evidenceHTML = "";

        if (evidence.length === 0) {
            evidenceHTML = `
                <div class="verification-empty">
                    No relevant evidence was found.
                </div>
            `;
        } else {
            evidenceHTML = evidence.map(source => `
                <article class="evidence-item">

                    <div class="evidence-header">

                        <span class="evidence-source">
                            ${getSourceName(source)}
                        </span>

                        <span class="evidence-score">
                            ${source.relevance_score ?? 0}% relevance
                        </span>

                    </div>

                    <h4>
                        ${source.title || "Untitled source"}
                    </h4>

                    <p>
                        ${source.description || "No description available."}
                    </p>

                    ${source.url
                    ? `
                                <a
                                    href="${source.url}"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                >
                                    Read source →
                                </a>
                            `
                    : ""
                }

                </article>
            `).join("");
        }

        let explanation;

        if (status === "SUPPORTED") {
            explanation =
                "Relevant evidence was found that supports this claim.";
        } else if (status === "CONTRADICTED") {
            explanation =
                "Relevant evidence was found that conflicts with this claim.";
        } else if (status === "RELATED") {
            explanation =
                "Related evidence was found, but it does not directly verify this claim.";
        } else {
            explanation =
                evidence.length
                    ? "Evidence was found, but it was not sufficient to verify this claim."
                    : "No sufficiently relevant evidence was found to verify this claim.";
        }

        card.innerHTML = `
            <div class="verification-header">

                <div>

                    <p class="verification-label">
                        Claim
                    </p>

                    <p class="verification-claim">
                        ${item.claim || "Unknown claim"}
                    </p>

                </div>

                <span class="verification-status ${status.toLowerCase()}">
                    ${status}
                </span>

            </div>

            <div class="verification-explanation">
                ${explanation}
            </div>

            <h4 class="evidence-heading">
                ${evidence.length ? "Related Evidence" : "Evidence Search"}
            </h4>

            <div class="evidence-list">
                ${evidenceHTML}
            </div>
        `;

        elements.verificationResults.appendChild(card);
    });
}

// ---------------------------
// Prediction
// ---------------------------

function renderPrediction(data) {
    const prediction = data.distilbert.prediction;
    const confidence = parseFloat(data.distilbert.confidence);

    const icon = document.getElementById("predictionIcon");
    const description = document.getElementById("predictionDescription");

    if (prediction === "FAKE") {
        elements.verdict.textContent = "Likely Fake";
        icon.innerHTML = "⚠";
        icon.className = "prediction-icon fake";

        description.textContent =
            "This article contains multiple indicators commonly associated with misinformation.";
    } else {
        elements.verdict.textContent = "Likely Credible";
        icon.innerHTML = "✓";
        icon.className = "prediction-icon real";

        description.textContent =
            "No major misinformation patterns were detected in the submitted article.";
    }

    elements.verdict.className =
        `prediction-badge ${prediction.toLowerCase()}`;

    elements.confidence.textContent =
        `${confidence.toFixed(1)}%`;

    const fill = document.getElementById("confidenceFill");

    fill.style.width = "0%";

    setTimeout(() => {
        fill.style.width = `${confidence}%`;
    }, 100);

    elements.bertVerdict.textContent =
        prediction === "FAKE"
            ? "⚠ Likely Fake"
            : "✓ Credible";

    elements.bertVerdict.className =
        `model-result ${prediction.toLowerCase()}`;

    elements.baselineVerdict.textContent =
        data.baseline.prediction === "FAKE"
            ? "⚠ Likely Fake"
            : "✓ Credible";

    elements.baselineVerdict.className =
        `model-result ${data.baseline.prediction.toLowerCase()}`;

    elements.whyFlagged.textContent =
        data.analysis.why_flagged;

    elements.factCheckNote.textContent =
        data.analysis.fact_check_note;

    elements.riskSignals.innerHTML = "";

    const signalIcons = {
        "Emotional Language": "⚠️",
        "Sensational Wording": "📢",
        "Clickbait": "📰",
        "Clickbait Pattern": "📰",
        "Unsupported Claims": "❓",
        "Fear Appeal": "🚨",
        "Bias": "⚖️",
        "Exaggeration": "📈",
        "Unverified Sources": "🔍"
    };

    if (data.analysis.risk_signals.length === 0) {
        elements.riskSignals.innerHTML =
            `<div class="signal-chip">✅ No significant risk signals detected</div>`;
    } else {
        data.analysis.risk_signals.forEach(signal => {
            const chip = document.createElement("div");

            chip.className = "signal-chip";

            chip.innerHTML = `
                <span>${signalIcons[signal] || "•"}</span>
                <span>${signal}</span>
            `;

            elements.riskSignals.appendChild(chip);
        });
    }

    // Render verification once.
    renderVerification(
        Array.isArray(data.verification)
            ? data.verification
            : data.verification
                ? [data.verification]
                : []
    );

    elements.result.style.display = "block";
}

updateStats();

// ---------------------------
// Copy report
// ---------------------------

document.getElementById("copyReportBtn").addEventListener("click", async () => {
    const report = `
VeriNews AI Report

Prediction:
${elements.verdict.textContent}

Confidence:
${elements.confidence.textContent}

Summary:
${elements.whyFlagged.textContent}

Recommendation:
${elements.factCheckNote.textContent}

Risk Signals:
${Array.from(document.querySelectorAll(".signal-chip"))
            .map(x => x.innerText)
            .join(", ")}

Generated:
${document.getElementById("analysisDate").textContent}
`;

    await navigator.clipboard.writeText(report);

    const btn = document.getElementById("copyReportBtn");

    btn.textContent = "Copied ✓";

    setTimeout(() => {
        btn.textContent = "Copy Report";
    }, 1800);
});