import time
import json
import logging
import asyncio

from pathlib import Path
from typing import Any, AsyncIterator
from openai import AsyncOpenAI

from app.schemas.generation import GenerationResult
from app.utils.streamed_json_response import StreamedResponseExtractor
from app.observability.logger import audit_event


logger = logging.getLogger(__name__)

PROMPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / "prompts"
)

MARKETING_PROMPT_PATH = (
    PROMPTS_DIR / "generation_marketing_v1.md"
)

INVENTORY_PROMPT_PATH = (
    PROMPTS_DIR / "generation_inventory_v1.md"
)

AVAILABILITY_PROMPT_PATH = (
    PROMPTS_DIR / "generation_availability_v1.md"
)

BANK_DETAILS_PROMPT_PATH = (
    PROMPTS_DIR / "generation_bank_details_v1.md"
)

SALES_OFFER_PROMPT_PATH = (
    PROMPTS_DIR / "generation_sales_offer_v1.md"
)

PROJECT_INFORMATION_PROMPT_PATH = (
    PROMPTS_DIR / "generation_project_information_v1.md"
)

WALKTHROUGH_PROMPT_PATH = (
    PROMPTS_DIR / "generation_walkthrough_v1.md"
)


class GenerationService:

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
    ):
        self.client = client
        self.model = model

        # Existing Marketing prompt
        self.marketing_prompt = (
            MARKETING_PROMPT_PATH.read_text(
                encoding="utf-8"
            )
        )

        # New Inventory prompt
        self.inventory_prompt = (
            INVENTORY_PROMPT_PATH.read_text(
                encoding="utf-8"
            )
        )

        # Availability prompt
        self.availability_prompt = (
            AVAILABILITY_PROMPT_PATH.read_text(
                encoding="utf-8"
            )
        )

        self.bank_details_prompt = (
            BANK_DETAILS_PROMPT_PATH.read_text(
                encoding="utf-8"
            )
        )

        self.sales_offer_prompt = (
            SALES_OFFER_PROMPT_PATH.read_text(
                encoding="utf-8"
            )
        )

        self.project_information_prompt = (
            PROJECT_INFORMATION_PROMPT_PATH.read_text(
                encoding="utf-8"
            )
        )

        self.walkthrough_prompt = (
            WALKTHROUGH_PROMPT_PATH.read_text(
                encoding="utf-8"
            )
        )

        # Preserve existing attribute for compatibility
        self.system_prompt = self.marketing_prompt

    def _select_prompt(
        self,
        intents: list[str],
        service_results: dict[str, Any],
    ) -> str:
        """
        Select response generation instructions
        based on verified service results and intents.
        """

        service = service_results.get("service")

        # 1. Inventory-only request
        if (
            service == "inventory"
            and set(intents) == {"inventory"}
        ):
            return self.inventory_prompt

        # 2. Marketing-only request
        if (
            service == "marketing"
            and set(intents) == {"marketing"}
        ):
            return self.marketing_prompt

        # 3. Download Availability only
        if (
            service == "download_availability"
            and set(intents) == {"download_availability"}
        ):
            return self.availability_prompt

        # 4. Bank Details

        if (
            service == "bank_details"
            and set(intents) == {"bank_details"}
        ):
            return self.bank_details_prompt

        # 4. Sales Offer

        if (
            service == "sales_offer"
            and set(intents) == {"sales_offer"}
        ):
            return self.sales_offer_prompt

        # 5. Project Information

        if (
            service == "project_information"
            and set(intents) == {"project_information"}
        ):
            return self.project_information_prompt

        # 6. Excel Walkthrough

        if (
            service == "excel_walkthrough"
            and set(intents) == {"excel_walkthrough"}
        ):
            return self.walkthrough_prompt

        # 7. Multi-intent request
        if service == "multi_intent":

            results = service_results.get("results", [])

            service_types = {
                item.get("service")
                for item in results
                if isinstance(item, dict)
            }

            instructions = [
                (
                    "You are the Danube Properties "
                    "response generation assistant.\n"
                    "Generate one concise response using "
                    "only verified backend service results.\n"
                    "Handle each requested service separately.\n"
                    "Never invent project names, unit details, "
                    "prices, availability, files, or links.\n"
                    "Follow the detected language.\n"
                    "Return the structured GenerationResult "
                    "with response and followups.\n"
                )
            ]

            if "marketing" in service_types:
                instructions.append(
                    "\n## Marketing Instructions\n"
                    + self.marketing_prompt
                )

            if "inventory" in service_types:
                instructions.append(
                    "\n## Inventory Instructions\n"
                    + self.inventory_prompt
                )

            if "download_availability" in service_types:
                instructions.append(
                    "\n## Download Availability Instructions\n"
                    + self.availability_prompt
                )

            if "bank_details" in service_types:
                instructions.append(
                    "\n## Bank Details Instructions\n"
                    + self.bank_details_prompt
                )

            if "sales_offer" in service_types:
                instructions.append(
                    "\n## Sales Offer Instructions\n"
                    + self.sales_offer_prompt
                )

            if "project_information" in service_types:
                instructions.append(
                    "\n## Project Information Instructions\n"
                    + self.project_information_prompt
                )

            if "excel_walkthrough" in service_types:
                instructions.append(
                    "\n## Excel Walkthrough Instructions\n"
                    + self.walkthrough_prompt
                )
                
            return "\n\n".join(instructions)

        # 8. Fallback for existing functionalities
        return self.system_prompt

        def _log_llm2_input(
            self,
            *,
            mode: str,
            message: str,
            language: str,
            intents: list[str],
            service_results: dict,
            history: list[dict] | None,
            selected_prompt: str,
        ):
            audit_event(
                "LLM2_INPUT",
                status="started",
                mode=mode,
                model=self.model,
                language=language,
                intents=intents,
                service=service_results.get("service"),
                message_length=len(message),
                history_count=len(history or []),
                input_keys=[
                    "user_message",
                    "detected_language",
                    "detected_intents",
                    "verified_service_results",
                    "recent_conversation",
                ],
                system_prompt_length=len(selected_prompt),
            )

    def _log_llm2_result(
        self,
        *,
        mode: str,
        generated: GenerationResult,
        started_at: float,
    ):
        latency_ms = round(
            (time.perf_counter() - started_at) * 1000,
            2,
        )

        audit_event(
            "LLM2_OUTPUT",
            status="success",
            mode=mode,
            response_length=len(generated.response),
            latency_ms=latency_ms,
        )

        audit_event(
            "FOLLOWUP_CHIPS_GENERATED",
            status="success",
            mode=mode,
            count=len(generated.followups),
        )


    def _log_llm2_input(
        self,
        *,
        mode,
        message,
        language,
        intents,
        service_results,
        history,
        selected_prompt,
    ):
        audit_event(
            "LLM2_INPUT",
            status="started",
            mode=mode,
            model=self.model,
            language=language,
            intents=intents,
            service=service_results.get("service"),
            message_length=len(message),
            history_count=len(history or []),
            system_prompt_length=len(selected_prompt),
        )

    def _log_llm2_result(
        self,
        *,
        mode,
        generated,
        started_at,
    ):
        latency_ms = round(
            (time.perf_counter() - started_at) * 1000,
            2,
        )

        audit_event(
            "LLM2_OUTPUT",
            status="success",
            mode=mode,
            response_length=len(generated.response),
            latency_ms=latency_ms,
        )

        audit_event(
            "FOLLOWUP_CHIPS_GENERATED",
            status="success",
            mode=mode,
            count=len(generated.followups),
        )

    async def generate(
        self,
        message: str,
        language: str,
        intents: list[str],
        service_results: dict[str, Any],
        history: list[dict] | None = None,
    ) -> GenerationResult:

        # 1. Select prompt based on service
        selected_prompt = self._select_prompt(
            intents=intents,
            service_results=service_results,
        )

        # 2. Prepare LLM input
        payload = {
            "user_message": message,
            "detected_language": language,
            "detected_intents": intents,
            "verified_service_results": service_results,
            "recent_conversation": history or [],
        }

        started_at = time.perf_counter()

        self._log_llm2_input(
            mode="standard",
            message=message,
            language=language,
            intents=intents,
            service_results=service_results,
            history=history,
            selected_prompt=selected_prompt,
        )

        try:
            # 3. Call Microsoft Foundry
            result = await self.client.responses.parse(
                model=self.model,
                instructions=selected_prompt,
                input=json.dumps(
                    payload,
                    ensure_ascii=False,
                    default=str,
                ),
                text_format=GenerationResult,
            )

            # 4. Extract structured response
            generated = result.output_parsed

            if generated is None:
                raise ValueError(
                    "Generation returned no parsed output"
                )

            if not generated.response.strip():
                raise ValueError(
                    "Generation returned empty response"
                )
            

            # 5. Clean and limit follow-up chips
            generated = self._postprocess_result(
                generated=generated,
                intents=intents,
                service_results=service_results,
            )

            # 6. Logging
            self._log_llm2_result(
                mode="standard",
                generated=generated,
                started_at=started_at,
            )

            return generated

        except Exception as exc:
            audit_event(
                "LLM2_FAILED",
                level="ERROR",
                status="failed",
                mode="standard",
                error_type=type(exc).__name__,
                latency_ms=round(
                    (time.perf_counter() - started_at) * 1000,
                    2,
                ),
            )
            raise

    async def generate_stream(
        self,
        message: str,
        language: str,
        intents: list[str],
        service_results: dict[str, Any],
        history: list[dict] | None = None,
    ) -> AsyncIterator[tuple[str, Any]]:

        # 1. Select prompt based on service
        selected_prompt = self._select_prompt(
            intents=intents,
            service_results=service_results,
        )

        # 2. Prepare LLM input
        payload = {
            "user_message": message,
            "detected_language": language,
            "detected_intents": intents,
            "verified_service_results": service_results,
            "recent_conversation": history or [],
        }

        started_at = time.perf_counter()

        self._log_llm2_input(
            mode="stream",
            message=message,
            language=language,
            intents=intents,
            service_results=service_results,
            history=history,
            selected_prompt=selected_prompt,
        )

        try:

            extractor = StreamedResponseExtractor()

            async with self.client.responses.stream(
                model=self.model,
                instructions=selected_prompt,
                input=json.dumps(
                    payload,
                    ensure_ascii=False,
                    default=str,
                ),
                text_format=GenerationResult,
            ) as stream:

                async for event in stream:

                    if event.type == "response.output_text.delta":

                        text = extractor.feed(event.delta)

                        if text:
                            yield ("token", text)

                final_response = await stream.get_final_response()

            generated = final_response.output_parsed

            if generated is None:
                raise ValueError(
                    "Streaming returned no parsed output"
                )

            if not generated.response.strip():
                raise ValueError(
                    "Streaming returned an empty response"
                )

            if not extractor.finished:
                raise ValueError(
                    "Streaming response field was incomplete"
                )

            if extractor.emitted != generated.response:
                raise ValueError(
                    "Streamed text does not match final response"
                )

            generated = self._postprocess_result(
                generated=generated,
                intents=intents,
                service_results=service_results,
            )

            audit_event(
                "LLM2_OUTPUT",
                llm2_response=generated.model_dump_json(),
            )


            self._log_llm2_result(
                mode="stream",
                generated=generated,
                started_at=started_at,
            )

            yield ("result", generated)
        
        except asyncio.CancelledError:
            audit_event(
                "LLM2_STREAM_CANCELLED",
                status="cancelled",
                mode="stream",
                latency_ms=round(
                    (time.perf_counter() - started_at) * 1000,
                    2,
                ),
            )
            raise

        except Exception as exc:
            audit_event(
                "LLM2_FAILED",
                level="ERROR",
                status="failed",
                mode="stream",
                error_type=type(exc).__name__,
                latency_ms=round(
                    (time.perf_counter() - started_at) * 1000,
                    2,
                ),
            )
            raise
    
    def _postprocess_result(
        self,
        generated: GenerationResult,
        intents: list[str],
        service_results: dict[str, Any],
    ) -> GenerationResult:

        if generated is None:
            raise ValueError(
                "Generation returned no parsed output"
            )

        if not generated.response.strip():
            raise ValueError(
                "Generation returned empty response"
            )

        # Preserve Excel Walkthrough RBAC behavior
        if (
            service_results.get("service")
            == "excel_walkthrough"
            and set(intents) == {"excel_walkthrough"}
        ):
            allowed_features = service_results.get(
                "allowed_followup_features", []
            )

            allowed_lookup = {
                feature.casefold(): feature
                for feature in allowed_features
            }

            validated_features = []

            for suggestion in generated.followups:
                if not isinstance(suggestion, str):
                    continue

                feature = allowed_lookup.get(
                    suggestion.strip().casefold()
                )

                if (
                    feature
                    and feature not in validated_features
                ):
                    validated_features.append(feature)

                if len(validated_features) == 3:
                    break

            generated.followups = [
                f"How do I use {feature}?"
                for feature in validated_features
            ]

        else:
            generated.followups = [
                chip.strip()
                for chip in generated.followups
                if isinstance(chip, str)
                and chip.strip()
            ][:3]

        return generated


def build_marketing_generation_context(
    project_name: str,
    requested_asset_types: list[str],
    files: list[dict],
    *,
    project_details: dict | None = None,
) -> dict:
    """
    Build a safe, compact marketing summary
    for LLM response generation.

    Files and project details must already have
    been validated by MarketingService.
    """

    asset_summary = []

    for file in files:
        asset_summary.append(
            {
                "name": file.get("name", ""),
                "type": file.get("type", ""),
                "format": file.get("format", ""),
            }
        )

    return {
        "service": "marketing",
        "project": project_name,
        "requested_asset_types": requested_asset_types,
        "assets_found": len(files) > 0,
        "asset_count": len(files),
        "available_assets": asset_summary,
        "verified_project_details": (
            project_details or {}
        ),
    }