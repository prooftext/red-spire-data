from __future__ import annotations

from typing import List
import math

try:
    import spacy
except ImportError:  # pragma: no cover - optional dependency
    spacy = None

try:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
except ImportError:  # pragma: no cover - optional dependency
    torch = None
    AutoModelForSequenceClassification = None
    AutoTokenizer = None

_SPACY_NLP = None
_TRANSFORMER = None

TRANSFORMER_MODEL = "roberta-base-openai-detector"

# TODO: Add keystroke-sequence transformer baseline (TempCharBERT/TypeFormer style)
# when enough per-user keystroke datasets are collected and labeled.


def _get_spacy():
    global _SPACY_NLP
    if _SPACY_NLP is not None:
        return _SPACY_NLP
    if spacy is None:
        return None
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    _SPACY_NLP = nlp
    return _SPACY_NLP


def _get_transformer():
    global _TRANSFORMER
    if _TRANSFORMER is not None:
        return _TRANSFORMER
    if AutoTokenizer is None or AutoModelForSequenceClassification is None:
        return None
    tokenizer = AutoTokenizer.from_pretrained(TRANSFORMER_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(TRANSFORMER_MODEL)
    _TRANSFORMER = (tokenizer, model)
    return _TRANSFORMER


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


def spacy_baseline_score(text: str) -> dict | None:
    nlp = _get_spacy()
    if nlp is None:
        return None

    doc = nlp(text)
    tokens = [t for t in doc if not t.is_space]
    words = [t for t in tokens if t.is_alpha]
    total_words = len(words)
    if total_words == 0:
        return {"name": "spacy_baseline_v1", "score": 0.0, "label": "HUMAN"}

    unique_words = len({t.lower_ for t in words})
    lexical_div = _safe_div(unique_words, total_words)

    stop_words = sum(1 for t in words if t.is_stop)
    stop_ratio = _safe_div(stop_words, total_words)

    bigrams = list(zip(words, words[1:]))
    bigram_total = len(bigrams)
    bigram_unique = len({(a.lower_, b.lower_) for a, b in bigrams})
    bigram_rep = 1.0 - _safe_div(bigram_unique, bigram_total) if bigram_total else 0.0

    sentences = list(doc.sents)
    sentence_count = len(sentences) or 1
    avg_sentence_len = _safe_div(total_words, sentence_count)

    lex_signal = _clamp((0.6 - lexical_div) / 0.6)
    rep_signal = _clamp(bigram_rep / 0.2)
    stop_signal = _clamp(stop_ratio / 0.6)
    length_signal = _clamp(avg_sentence_len / 30.0)

    score = 0.4 * lex_signal + 0.3 * rep_signal + 0.2 * stop_signal + 0.1 * length_signal
    score = _clamp(score)
    label = "AI" if score >= 0.5 else "HUMAN"

    return {
        "name": "spacy_baseline_v1",
        "score": score,
        "label": label,
    }


def transformer_score(text: str) -> dict | None:
    if torch is None:
        return None

    transformer = _get_transformer()
    if transformer is None:
        return None

    tokenizer, model = transformer
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits[0]
    probs = torch.softmax(logits, dim=-1)
    labels = [model.config.id2label[i] for i in range(len(probs))]

    ai_score = None
    for label, prob in zip(labels, probs.tolist()):
        if label.upper() in {"FAKE", "AI", "MACHINE"}:
            ai_score = prob
            break
    if ai_score is None:
        ai_score = probs.max().item()

    label = "AI" if ai_score >= 0.5 else "HUMAN"

    return {
        "name": TRANSFORMER_MODEL,
        "score": float(ai_score),
        "label": label,
    }


def run_detectors(text: str) -> List[dict]:
    results = []
    spacy_result = spacy_baseline_score(text)
    if spacy_result:
        results.append(spacy_result)

    transformer_result = transformer_score(text)
    if transformer_result:
        results.append(transformer_result)

    return results
