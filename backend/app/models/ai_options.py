from pydantic import BaseModel


class AIOptions(BaseModel):
    inferOpeningCredits: bool = True
    inferEndCredits: bool = True
    deselectNonChapters: bool = False
    keepDeselectedTitles: bool = False
    usePreferredTitles: bool = False
    preferredTitlesSource: str = ""
    additionalInstructions: str = ""
    provider_id: str = ""
    model_id: str = ""
