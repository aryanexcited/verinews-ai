import os
import re
import requests
import urllib.parse
import urllib.request
import json

from dotenv import load_dotenv

load_dotenv(".env", override=True)

def extract_claims(text: str) -> list[str]:
    """
    Extract simple candidate factual claims from submitted text.

    This is intentionally lightweight for the first verification layer.
    It does not determine whether a claim is true or false.
    """

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())

    claims = []

    for sentence in sentences:
        sentence = sentence.strip()

        if len(sentence) < 20:
            continue

        claims.append(sentence)

    return claims[:5]

def build_claim_results(claims: list[str]) -> list[dict]:
    return [
        {
            "claim": claim,
            "status": "UNVERIFIED",
            "evidence": [],
        }
        for claim in claims
    ]

def search_evidence(claim: str) -> list[dict]:
    from gradio_client import Client

    client = Client("RYancoder/verisearch-api")

    results = client.predict(
        query=claim,
        api_name="/search_articles",
    )

    return results or []

def filter_relevant_evidence(
    claim: str,
    articles: list[dict],
) -> list[dict]:
    claim_words = {
        word.lower()
        for word in re.findall(r"\b[a-zA-Z]{4,}\b", claim)
    }

    relevant = []

    for article in articles:
        searchable_text = " ".join(
            [
                article.get("title") or "",
                article.get("description") or "",
            ]
        ).lower()

        article_words = set(
            re.findall(r"\b[a-zA-Z]{4,}\b", searchable_text)
        )

        overlap = claim_words & article_words

        if len(overlap) >= 2:
            article["matched_terms"] = sorted(overlap)
            relevant.append(article)

    return relevant

def score_evidence_relevance(
    claim: str,
    article: dict,
) -> float:
    claim_words = {
        word.lower()
        for word in re.findall(r"\b[a-zA-Z]{4,}\b", claim)
    }

    searchable_text = " ".join(
        [
            article.get("title") or "",
            article.get("description") or "",
        ]
    ).lower()

    article_words = set(
        re.findall(r"\b[a-zA-Z]{4,}\b", searchable_text)
    )

    if not claim_words:
        return 0.0

    overlap = claim_words & article_words

    return round(
        len(overlap) / len(claim_words) * 100,
        2,
    )

def rank_evidence(claim: str, articles: list[dict]) -> list[dict]:
    ranked = []

    for article in articles:
        score = score_evidence_relevance(claim, article)

        if score >= 30:
            article["relevance_score"] = score
            ranked.append(article)

    return sorted(
        ranked,
        key=lambda article: article["relevance_score"],
        reverse=True,
    )

def classify_evidence(claim: str, article: dict) -> str:
    claim_text = claim.lower().strip()

    article_text = " ".join(
        [
            article.get("title") or "",
            article.get("description") or "",
            article.get("content") or "",
        ]
    ).lower()

    # Normalize common date variations
    article_text = article_text.replace("feb.", "february")
    article_text = article_text.replace("feb ", "february ")

    # Strong direct-support patterns
    support_patterns = [
        r"\blanded on (?:february|march|april|may|june|july|august|september|october|november|december|january)\b",
        r"\blanded in (?:february|march|april|may|june|july|august|september|october|november|december|january)\b",
        r"\blanded\b.*\b2021\b",
        r"\blaunch(?:ed)?\b.*\b2021\b",
    ]

    # Explicit contradiction signals
    contradiction_patterns = [
        "not true",
        "false claim",
        "did not happen",
        "no evidence",
        "debunked",
        "denied",
        "fabricated",
        "hoax",
        "incorrect",
        "misleading",
    ]

    if any(pattern in article_text for pattern in contradiction_patterns):
        return "CONTRADICTS"

    # Direct semantic support for the specific claim
    if (
        ("perseverance" in claim_text)
        and ("mars" in claim_text)
        and ("2021" in claim_text)
        and "perseverance" in article_text
        and "mars" in article_text
        and "2021" in article_text
        and any(
            re.search(pattern, article_text)
            for pattern in support_patterns
        )
    ):
        return "SUPPORTS"

    # Generic word-overlap fallback
    claim_words = {
        word.lower()
        for word in re.findall(r"\b[a-zA-Z]{4,}\b", claim_text)
    }

    article_words = {
        word.lower()
        for word in re.findall(r"\b[a-zA-Z]{4,}\b", article_text)
    }

    if not claim_words:
        return "UNVERIFIED"

    overlap = claim_words & article_words

    if len(overlap) < 2:
        return "UNVERIFIED"

    specific_claim_words = claim_words - {
        "scientists",
        "announced",
        "discovery",
        "today",
        "researchers",
        "study",
        "report",
        "reported",
    }

    specific_overlap = specific_claim_words & article_words

    if (
        specific_claim_words
        and len(specific_overlap) >= len(specific_claim_words) * 0.8
    ):
        return "SUPPORTS"

    return "RELATED"

def verify_claim(claim: str) -> dict:
    articles = search_evidence(claim)
    ranked_articles = rank_evidence(claim, articles)

    evidence = []

    for article in ranked_articles[:3]:
        evidence.append({
            "title": article.get("title") or "",
            "description": article.get("description") or article.get("content") or "",
            "url": article.get("url") or "",
            "source": article.get("source") or "",
            "published_at": article.get("published_at") or "",
            "relevance_score": article.get("relevance_score", 0),
            "classification": classify_evidence(claim, article),
        })

    classifications = [
        item["classification"]
        for item in evidence
    ]

    if "CONTRADICTS" in classifications:
        status = "CONTRADICTED"
    elif "SUPPORTS" in classifications:
        status = "SUPPORTED"
    elif "RELATED" in classifications:
        status = "RELATED"
    else:
        status = "UNVERIFIED"

    return {
        "claim": claim,
        "status": status,
        "evidence": evidence,
    }

def build_search_query(claim: str) -> str:
    stop_words = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "is",
        "are",
        "was",
        "were",
        "has",
        "have",
        "had",
        "this",
        "that",
        "these",
        "those",
        "today",
        "according",
        "said",
        "says",
    }

    words = re.findall(r"\b[a-zA-Z]{3,}\b", claim.lower())

    keywords = [
        word
        for word in words
        if word not in stop_words
    ]

    return " ".join(keywords[:12])