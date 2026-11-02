"""Stage 4 - Pydantic Case Brief synthesis.

Converts retrieved context chunks into a strictly-typed JSON Case Brief using
Groq Llama 3.3 70B (via instructor). Every factual item carries a mandatory
`source_id`; after extraction, any item whose `source_id` does not map to a real
retrieved source is dropped, enforcing auditable traceability.

The brief is the single structured artifact the generator (Stage 5) writes from.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from src.logger import get_logger

if TYPE_CHECKING:
    from src.indexing import RetrievedChunk

log = get_logger(__name__)


# --- typed sub-models (each fact is source-anchored) ----------------------- #
class TimelineEvent(BaseModel):
    date: str = Field(description="Year or date of the event, e.g. '2021' or 'Q3 2022'")
    event: str
    source_id: str


class Intervention(BaseModel):
    name: str
    methodology: str = Field(default="", description="e.g. Lean Six Sigma, TQM, Kaizen, TPM, ISO 9001")
    description: str = Field(default="", description="Brief description of the intervention")
    source_id: str


class Stakeholder(BaseModel):
    name: str
    role: str = ""
    interest: str = Field(default="", description="Their stake or conflicting interest in the decision")
    source_id: str


class FinancialDatum(BaseModel):
    metric: str
    value: str
    year: str = ""
    source_id: str


class ExecutiveQuote(BaseModel):
    quote: str
    speaker: str
    role: str = ""
    source_id: str


class Tension(BaseModel):
    description: str = Field(description="A dilemma or conflict that creates narrative tension")
    source_id: str


class ResultImpact(BaseModel):
    description: str
    metric: str = ""
    value: str = ""
    source_id: str


class Protagonist(BaseModel):
    name: str
    designation: str = ""
    decision_context: str = Field(default="", description="The crossroad/decision they faced")
    decision_timeframe: str = ""
    source_id: str = ""


class Citation(BaseModel):
    source_id: str
    title: str
    origin: str = Field(description="File path or URL")


class CaseBrief(BaseModel):
    """Strict, source-anchored intermediate representation of the case."""

    company: str
    protagonist: Protagonist
    industry_macro_context: str = ""
    historical_timeline: list[TimelineEvent] = Field(default_factory=list)
    quality_operational_bottleneck: list[Tension] = Field(default_factory=list)
    strategic_interventions: list[Intervention] = Field(default_factory=list)
    applied_quality_toolkits: list[str] = Field(default_factory=list)
    stakeholders_map: list[Stakeholder] = Field(default_factory=list)
    financial_appendix_data: list[FinancialDatum] = Field(default_factory=list)
    verified_executive_quotes: list[ExecutiveQuote] = Field(default_factory=list)
    tensions_and_dilemmas: list[Tension] = Field(default_factory=list)
    results_and_impact: list[ResultImpact] = Field(default_factory=list)
    learning_outcomes: list[str] = Field(default_factory=list)
    source_citations_manifest: list[Citation] = Field(default_factory=list)


_SYSTEM = (
    "You are a meticulous business-case research analyst. You read retrieved source "
    "passages (each tagged with a [source_id]) about a company and extract a strictly "
    "factual, structured Case Brief. RULES: (1) Use ONLY information present in the "
    "passages. (2) Every factual field MUST cite the exact [source_id] it came from. "
    "(3) Never invent numbers, quotes, names, or dates. (4) If something is not "
    "supported by a passage, omit it rather than guessing. (5) Keep descriptions highly "
    "concise. To prevent token cutoff during output generation, limit all list arrays "
    "(timeline events, bottlenecks, quotes, stakeholder mappings, financial rows) to a "
    "maximum of 5 unique, high-importance items."
)


def _build_context(contexts: list["RetrievedChunk"], max_chars: int = 24000) -> str:
    """Render retrieved chunks as a source-tagged context block for the LLM."""
    parts: list[str] = []
    used = 0
    for rc in contexts:
        ch = rc.chunk
        block = f"[{ch.source_id}] (title: {ch.title})\n{ch.raw_text}\n"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)


def _valid_source_ids(contexts: list["RetrievedChunk"]) -> set[str]:
    return {rc.chunk.source_id for rc in contexts}


def _drop_unsourced(brief: CaseBrief, valid: set[str]) -> CaseBrief:
    """Remove any sourced item whose source_id is empty or not in `valid`."""

    def keep(item: BaseModel) -> bool:
        sid = getattr(item, "source_id", "")
        return bool(sid) and sid in valid

    brief.historical_timeline = [x for x in brief.historical_timeline if keep(x)]
    brief.quality_operational_bottleneck = [x for x in brief.quality_operational_bottleneck if keep(x)]
    brief.strategic_interventions = [x for x in brief.strategic_interventions if keep(x)]
    brief.stakeholders_map = [x for x in brief.stakeholders_map if keep(x)]
    brief.financial_appendix_data = [x for x in brief.financial_appendix_data if keep(x)]
    brief.verified_executive_quotes = [x for x in brief.verified_executive_quotes if keep(x)]
    brief.tensions_and_dilemmas = [x for x in brief.tensions_and_dilemmas if keep(x)]
    brief.results_and_impact = [x for x in brief.results_and_impact if keep(x)]
    # Manifest is rebuilt from real contexts below, so leave it for the caller.
    return brief


def build_case_brief(company: str, contexts: list["RetrievedChunk"]) -> CaseBrief:
    """Extract a source-anchored CaseBrief from retrieved context (Groq 70B)."""
    from src.llm_client import get_llm_client

    if not contexts:
        raise ValueError("No retrieved contexts provided; cannot build a brief.")

    # Normalize string contexts to RetrievedChunk objects if they are passed as raw strings
    normalized = []
    for rc in contexts:
        if isinstance(rc, str):
            source_id = "unknown"
            raw_text = rc
            if "Source: " in rc and "Content:\n" in rc:
                parts = rc.split("Content:\n", 1)
                raw_text = parts[1]
                header = parts[0]
                if "Source: " in header:
                    source_id = header.replace("Source: ", "").strip()
            
            from src.indexing import Chunk, RetrievedChunk
            mock_chunk = Chunk(
                chunk_id=f"{source_id}-mock",
                source_id=source_id,
                source_type="pdf" if source_id.lower().endswith(".pdf") else "text",
                title=source_id,
                origin=source_id,
                text=raw_text,
                raw_text=raw_text
            )
            normalized.append(RetrievedChunk(chunk=mock_chunk, score=1.0))
        else:
            normalized.append(rc)
    contexts = normalized

    client = get_llm_client()
    context_block = _build_context(contexts)
    prompt = (
        f"Company under study: {company}\n\n"
        f"Retrieved source passages:\n{context_block}\n\n"
        "Extract the structured Case Brief now. Cite a [source_id] for every factual "
        "item, using only the source_ids shown above."
    )

    log.info(f"Extracting Case Brief for {company!r} from {len(contexts)} contexts.")
    brief = client.structured(prompt, CaseBrief, system=_SYSTEM, max_tokens=6000)
    brief.company = company

    valid = _valid_source_ids(contexts)
    brief = _drop_unsourced(brief, valid)
    # Rebuild an accurate citation manifest from the real contexts that survived.
    seen: dict[str, Citation] = {}
    for rc in contexts:
        ch = rc.chunk
        seen.setdefault(ch.source_id, Citation(source_id=ch.source_id, title=ch.title, origin=ch.origin))
    brief.source_citations_manifest = list(seen.values())

    log.info(
        f"Case Brief built: {len(brief.historical_timeline)} events, "
        f"{len(brief.strategic_interventions)} interventions, "
        f"{len(brief.verified_executive_quotes)} quotes, "
        f"{len(brief.source_citations_manifest)} sources."
    )
    return brief
# =====================================================================
# AUTOMATED PIPELINE BRIDGE LAYER (LEAVES WARP'S CODE UNTOUCHED)
# =====================================================================
import inspect
from pydantic import BaseModel

# 1. Dynamically map the Pydantic brief case model class Warp built
for _name, _obj in list(globals().items()):
    if inspect.isclass(_obj) and issubclass(_obj, BaseModel) and _name != "BaseModel":
        if "Brief" in _name or "Case" in _name:
            PydanticCaseBrief = _obj
            break
else:
    PydanticCaseBrief = globals().get("CaseBrief", globals().get("Brief", BaseModel))

# 2. Dynamically map or wrap the brief generation function Warp built with signature mismatch resolution
def synthesize_case_brief(*args, **kwargs):
    target = globals().get('build_case_brief')
    if not target:
        for name, obj in list(globals().items()):
            if callable(obj) and not inspect.isclass(obj) and name != "synthesize_case_brief" and not name.startswith("_"):
                if any(k in name.lower() for k in ["brief", "synthesize", "generate", "build"]):
                    target = obj
                    break
    
    if not target:
        return "Error: Could not route to backend brief synthesis function."

    # Resolve signature mismatch (e.g. caller passed only contexts list, but function expects company first)
    sig = inspect.signature(target)
    params = list(sig.parameters.values())
    
    if len(params) == 2 and params[0].name == 'company' and params[1].name == 'contexts':
        contexts = None
        company = "Company"
        
        # If contexts is passed as the first positional argument
        if len(args) == 1 and isinstance(args[0], list):
            contexts = args[0]
        elif len(args) == 2:
            # If arguments are already (company, contexts) or (contexts, company)
            if isinstance(args[0], list):
                contexts = args[0]
                company = args[1]
            else:
                company = args[0]
                contexts = args[1]
        
        if 'contexts' in kwargs:
            contexts = kwargs['contexts']
        if 'company' in kwargs:
            company = kwargs['company']
            
        if contexts is not None:
            return target(company, contexts)

    return target(*args, **kwargs)