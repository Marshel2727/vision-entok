from typing import Literal

from pydantic import BaseModel, Field, model_validator


class EventReviewRequest(BaseModel):
    status: Literal["confirmed", "corrected", "ignored"]
    corrected_label: Literal["normal", "abnormal", "no_detection"] | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_correction(self):
        if self.status == "corrected" and not self.corrected_label:
            raise ValueError("corrected_label wajib untuk status corrected.")
        return self
