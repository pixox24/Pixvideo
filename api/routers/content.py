# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Content generation endpoints used by the React workbench."""

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.dependencies import PixelleVideoDep
from api.schemas.content import KeywordExtractRequest, KeywordExtractResponse
from pixelle_video.utils.content_generators import generate_highlight_keywords

router = APIRouter(prefix="/content", tags=["Content Generation"])


@router.post("/keywords", response_model=KeywordExtractResponse)
async def extract_keywords(
    request: KeywordExtractRequest,
    pixelle_video: PixelleVideoDep,
):
    """Extract highlight keywords (with suggested colors) from narration text."""
    try:
        logger.info(f"Extracting up to {request.max_keywords} highlight keywords")
        keywords = await generate_highlight_keywords(
            llm_service=pixelle_video.llm,
            text=request.text,
            max_keywords=request.max_keywords,
            style=request.style,
            density=request.density,
            avoid_words=request.avoid_words,
        )
        return KeywordExtractResponse(keywords=keywords)
    except Exception as e:
        logger.error(f"Keyword extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
