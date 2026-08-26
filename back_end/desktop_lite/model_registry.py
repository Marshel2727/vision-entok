from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .runtime_paths import RuntimePaths


@dataclass(frozen=True)
class ModelDefinition:
    id: str
    name: str
    bundled_filename: str
    development_path: str


MODELS: tuple[ModelDefinition, ...] = (
    ModelDefinition(
        id="normal-abnormal",
        name="Normal + Abnormal",
        bundled_filename="entok_normal_abnormal.pt",
        development_path="back_end/ai/runs/train/entok_eye_yolo26m_v4-3/weights/best.pt",
    ),
    ModelDefinition(
        id="normal-only",
        name="Normal Only",
        bundled_filename="entok_normal_only.pt",
        development_path="back_end/ai/runs/train/entok_eye_normal_only_yolo26m-6/weights/best.pt",
    ),
    ModelDefinition(
        id="normal-only-datav2-960",
        name="Normal Only - Data v2 960",
        bundled_filename="entok_normal_only_datav2_960.pt",
        development_path="back_end/ai/runs/train/entok_eye_normal_only_datav2_960-2/weights/best.pt",
    ),
)

DEFAULT_MODEL_ID = MODELS[0].id


def model_by_id(model_id: str) -> ModelDefinition:
    for model in MODELS:
        if model.id == model_id:
            return model
    raise ValueError(f"Model tidak dikenal: {model_id}")


def resolve_model_path(model: ModelDefinition, paths: RuntimePaths) -> Path:
    bundled_candidates = (
        paths.resource_root / "models" / model.bundled_filename,
        paths.resource_root
        / "back_end"
        / "desktop_lite"
        / "models"
        / model.bundled_filename,
    )
    for candidate in bundled_candidates:
        if candidate.is_file():
            return candidate.resolve()

    development_candidate = paths.resource_root / model.development_path
    if development_candidate.is_file():
        return development_candidate.resolve()

    raise FileNotFoundError(
        f"Model '{model.name}' tidak ditemukan. Dicari sebagai {model.bundled_filename}."
    )


def resolved_model_choices(paths: RuntimePaths) -> list[tuple[ModelDefinition, Path]]:
    return [(model, resolve_model_path(model, paths)) for model in MODELS]
