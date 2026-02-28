from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Theme(BaseModel):
    id: int | None = None
    uuid: str = ""
    owner_type: str = "user"  # "user", "organization", or "billing"
    owner_id: int = 0
    name: str = ""
    header_font: str = "Montserrat"
    text_font: str = "Montserrat"
    primary: str = "#8A4C94"
    primary_light: str = "#EEE4F1"
    secondary: str = "#6EAFAE"
    secondary_dark: str = "#357B7C"
    text_color: str = "#282830"
    text_contrast: str = "#FFFFFF"
    created_at: datetime | None = None
    updated_at: datetime | None = None


DEFAULT_THEME = Theme(
    name="Padrão",
    header_font="Montserrat",
    text_font="Montserrat",
    primary="#8A4C94",
    primary_light="#EEE4F1",
    secondary="#6EAFAE",
    secondary_dark="#357B7C",
    text_color="#282830",
    text_contrast="#FFFFFF",
)


AVAILABLE_FONTS: dict[str, dict[str, str]] = {
    "Montserrat": {
        "regular": "Montserrat-Regular.ttf",
        "bold": "Montserrat-Bold.ttf",
        "semibold": "Montserrat-SemiBold.ttf",
    },
    "Roboto": {"regular": "Roboto-Regular.ttf", "bold": "Roboto-Bold.ttf", "semibold": "Roboto-Medium.ttf"},
    "Lora": {"regular": "Lora-Regular.ttf", "bold": "Lora-Bold.ttf", "semibold": "Lora-SemiBold.ttf"},
    "Playfair Display": {
        "regular": "PlayfairDisplay-Regular.ttf",
        "bold": "PlayfairDisplay-Bold.ttf",
        "semibold": "PlayfairDisplay-SemiBold.ttf",
    },
    "Open Sans": {"regular": "OpenSans-Regular.ttf", "bold": "OpenSans-Bold.ttf", "semibold": "OpenSans-SemiBold.ttf"},
    "Source Sans 3": {
        "regular": "SourceSans3-Regular.ttf",
        "bold": "SourceSans3-Bold.ttf",
        "semibold": "SourceSans3-SemiBold.ttf",
    },
    "Merriweather": {
        "regular": "Merriweather-Regular.ttf",
        "bold": "Merriweather-Bold.ttf",
        "semibold": "Merriweather-Regular.ttf",
    },
    "Raleway": {"regular": "Raleway-Regular.ttf", "bold": "Raleway-Bold.ttf", "semibold": "Raleway-SemiBold.ttf"},
    "Oswald": {"regular": "Oswald-Regular.ttf", "bold": "Oswald-Bold.ttf", "semibold": "Oswald-Medium.ttf"},
    "Nunito": {"regular": "Nunito-Regular.ttf", "bold": "Nunito-Bold.ttf", "semibold": "Nunito-SemiBold.ttf"},
}
