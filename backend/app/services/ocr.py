from pathlib import Path
from typing import Callable


OCREngine = Callable[[Path], list[tuple[str, float]]]


class OCRService:
    def __init__(self, engine: OCREngine, min_confidence: float = 0.5) -> None:
        self.engine = engine
        self.min_confidence = min_confidence

    def process(self, image: Path) -> dict[str, str]:
        try:
            lines = self.engine(image)
            text = "\n".join(value for value, confidence in lines if confidence >= self.min_confidence)
            return {"status": "success", "text": text, "error": ""}
        except Exception as exc:
            return {"status": "failed", "text": "", "error": str(exc)}

    def process_many(self, images: list[Path]) -> list[dict[str, str]]:
        return [self.process(image) for image in images]
