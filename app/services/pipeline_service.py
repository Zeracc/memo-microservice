import hashlib
import re
from collections import Counter
from dataclasses import dataclass

from app.schemas.job import JobResult


STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "com",
    "da",
    "de",
    "do",
    "e",
    "em",
    "for",
    "in",
    "is",
    "na",
    "no",
    "o",
    "of",
    "on",
    "or",
    "para",
    "por",
    "que",
    "the",
    "to",
    "um",
    "uma",
}


@dataclass(slots=True)
class TextDocument:
    raw_text: str
    normalized_text: str
    document_id: str


class TextPipelineService:
    async def load_input(self, text: str) -> TextDocument:
        normalized_text = " ".join(text.split())
        document_id = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:16]
        return TextDocument(
            raw_text=text,
            normalized_text=normalized_text,
            document_id=document_id,
        )

    async def extract_metadata(self, document: TextDocument) -> dict[str, int]:
        words = self._tokenize(document.normalized_text)
        sentences = [chunk.strip() for chunk in re.split(r"[.!?]+", document.normalized_text) if chunk.strip()]
        return {
            "character_count": len(document.normalized_text),
            "word_count": len(words),
            "sentence_count": len(sentences),
        }

    async def analyze_content(
        self,
        document: TextDocument,
        metadata: dict[str, int],
    ) -> dict[str, object]:
        words = self._tokenize(document.normalized_text)
        filtered_words = [word for word in words if word not in STOPWORDS]
        keyword_counts = Counter(filtered_words)
        keywords = [word for word, _ in keyword_counts.most_common(5)]

        tone = "concise" if metadata["word_count"] < 25 else "detailed"
        estimated_reading_seconds = max(1, round(metadata["word_count"] / 3.2))

        return {
            "keywords": keywords,
            "tone": tone,
            "estimated_reading_seconds": estimated_reading_seconds,
        }

    async def generate_recommendations(
        self,
        metadata: dict[str, int],
        analysis: dict[str, object],
    ) -> list[str]:
        recommendations: list[str] = []

        if metadata["word_count"] < 20:
            recommendations.append("Expandir o contexto para enriquecer a analise.")
        else:
            recommendations.append("Destacar os pontos principais em um resumo executivo.")

        if metadata["sentence_count"] > 4:
            recommendations.append("Quebrar o texto em blocos menores para melhorar a leitura.")

        keywords = analysis.get("keywords", [])
        if isinstance(keywords, list) and keywords:
            recommendations.append(f"Priorizar os topicos: {', '.join(keywords[:3])}.")
        else:
            recommendations.append("Adicionar termos mais especificos para gerar insights melhores.")

        return recommendations

    async def build_result(
        self,
        document: TextDocument,
        metadata: dict[str, int],
        analysis: dict[str, object],
        recommendations: list[str],
    ) -> JobResult:
        keywords = [str(keyword) for keyword in analysis.get("keywords", [])]
        summary = (
            f"Texto com {metadata['word_count']} palavras, tom {analysis['tone']} "
            f"e foco em {', '.join(keywords[:3]) or 'temas gerais'}."
        )

        return JobResult(
            processed_text=document.normalized_text,
            document_id=document.document_id,
            summary=summary,
            keywords=keywords,
            recommendation_count=len(recommendations),
            completed_at=self._now(),
        )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"\b\w+\b", text.lower(), flags=re.UNICODE)

    @staticmethod
    def _now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
