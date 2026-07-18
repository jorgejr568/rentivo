from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

FontName = Literal[
    "Montserrat",
    "Roboto",
    "Lora",
    "Playfair Display",
    "Open Sans",
    "Source Sans 3",
    "Merriweather",
    "Raleway",
    "Oswald",
    "Nunito",
]
ThemeSource = Literal["billing", "organization", "user", "default"]
HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]

AVAILABLE_FONT_NAMES: tuple[FontName, ...] = (
    "Montserrat",
    "Roboto",
    "Lora",
    "Playfair Display",
    "Open Sans",
    "Source Sans 3",
    "Merriweather",
    "Raleway",
    "Oswald",
    "Nunito",
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ThemeUpdateRequest(_StrictModel):
    header_font: FontName
    text_font: FontName
    primary: HexColor
    primary_light: HexColor
    secondary: HexColor
    secondary_dark: HexColor
    text_color: HexColor
    text_contrast: HexColor


class ThemeValuesResponse(ThemeUpdateRequest):
    pass


class ThemeOptionsResponse(_StrictModel):
    fonts: tuple[FontName, ...] = AVAILABLE_FONT_NAMES


class ThemeCapabilitiesResponse(_StrictModel):
    can_edit: bool
    can_reset: bool


class ThemeResponse(_StrictModel):
    stored: ThemeValuesResponse | None
    effective: ThemeValuesResponse
    effective_source: ThemeSource
    options: ThemeOptionsResponse
    capabilities: ThemeCapabilitiesResponse
