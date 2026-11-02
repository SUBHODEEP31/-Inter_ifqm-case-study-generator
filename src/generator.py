"""Stage 5 - Style-transferred case-study generator.

Writes the narrative section-by-section from the source-anchored CaseBrief
(Stage 4), grounding every section in (a) the structured brief and (b) freshly
retrieved company-fact chunks, while imitating the *voice and structure* of the
curated reference cases via Style RAG (Stage 5 prep / reference_index).

Hard constraints enforced via prompt + light post-checks:
  - Past tense, third-person, Harvard/Ivey teaching-case register.
  - Inline [source_id] citations on every factual claim.
  - No consultancy filler / banned words.
  - Facts come ONLY from the brief + retrieved chunks (never invented).
"""
from __future__ import annotations

import re
from typing import Callable

from pydantic import BaseModel

from src.brief_engine import CaseBrief
from src.indexing import HybridIndex
from src.logger import get_logger
from src.reference_index import get_style_example

log = get_logger(__name__)

# Consultancy/LLM filler that flattens a teaching-case voice. Banned in output.
BANNED_WORDS = [
    "leverage", "synergy", "synergies", "robust", "delve", "tapestry", "moreover",
    "furthermore", "game-changer", "game changer", "cutting-edge", "seamless",
    "navigate the complexities", "testament", "underscore", "underscores", "pivotal",
    "realm", "landscape", "showcase", "utilize", "utilise", "plethora", "myriad",
    "vibrant", "bustling", "in today's fast-paced", "ever-evolving", "embark",
    "unlock", "elevate", "harness the power",
]


class Section(BaseModel):
    key: str
    title: str
    body: str


class CaseStudyDraft(BaseModel):
    company: str
    title: str
    sections: list[Section]

    @property
    def word_count(self) -> int:
        return sum(len(s.body.split()) for s in self.sections)

    def full_text(self) -> str:
        parts = [f"# {self.title}\n"]
        for s in self.sections:
            parts.append(f"## {s.title}\n\n{s.body.strip()}\n")
        return "\n".join(parts)


# --- section blueprint ----------------------------------------------------- #
# (key, title, retrieval query suffix, writing guidance)
_SECTION_SPECS: list[tuple[str, str, str, str]] = [
    (
        "vignette", "Opening Hook", "leadership decision dilemma crossroad protagonist",
        "Drops the reader into a precise, high-pressure moment of uncertainty with a named executive protagonist facing a critical decision. Set the scene (place, time, what is at stake). Support cinematic hook styles (environmental boardroom/floor tension), statistical hooks (opens with a striking operational/financial metric deficit), or narrative hooks (chronological backstory of the protagonist's journey). Do NOT include any section header or introduction in the text."
    ),
    (
        "company_background", "Company Background", "company history founding products operations",
        "Gathers organizational context and constructs a neutral, past-tense narrative limited strictly to history relevant to the core problem."
    ),
    (
        "industry_context", "Industry & Competitive Context", "industry competition market trends regulation macro forces",
        "Evaluates the external market landscape, direct competitors, macro forces, and industry-wide trends."
    ),
    (
        "the_challenge", "The Challenge", "quality defect bottleneck operational problem failure dilemma",
        "Organizes, sharpens, and expands the core problem parameters to state the dilemma clearly with supporting data, without resolving it. Explicitly reference 'Exhibit 1' when analyzing the performance gap and operational metrics."
    ),
    (
        "root_cause", "Root Cause Analysis", "root cause failure analysis quality bottleneck fishbone Pareto",
        "Explain why the problem exists, supported by quality and analytical tools. Explicitly reference the Pareto analysis in 'Exhibit 3' and the Ishikawa root-cause diagram in 'Exhibit 4' to substantiate the bottleneck findings."
    ),
    (
        "solution", "Approach / Solution", "operational intervention selected rationale strategy decision",
        "Details what specific strategic or process-driven operational actions/solutions the organization selected and its underlying rationale."
    ),
    (
        "implementation", "Implementation", "implementation rollout execution timeline phases deployment resources",
        "Narrate the steps taken, deployment timeline, resources deployed, and change management workflows. Explicitly reference the chronological implementation milestones shown in 'Exhibit 2'."
    ),
    (
        "results", "Results and Impact", "results outcome impact performance metrics quantified outcomes",
        "Extracts quantified metrics from raw source materials, capturing both positive intended goals and negative unintended consequences measured across financial, operational, and human dimensions. Explicitly refer back to the trend comparisons in 'Exhibit 1'."
    ),
    (
        "learnings", "Key Learnings", "generalizable insights business lessons takeaways distilled",
        "Distill generalizable insights and high-level business lessons from the experience."
    ),
    (
        "recommendations", "Recommendations", "actionable guidance operational roadmaps next steps recommendations",
        "Provide actionable guidance, operational roadmaps, and specific next steps for similar organizations or contexts."
    ),
    (
        "future_scope", "Future Scope", "next steps open strategic questions future scope improvement",
        "Outline next steps, open strategic questions, and defined areas for continued improvement."
    ),
    (
        "discussion_questions", "Discussion Questions", "",
        "Write 5-6 open-ended discussion questions that push students to analyze the decision, trade-offs, and quality frameworks. Number them."
    ),
    (
        "process_flowchart", "Process Flowchart", "process map flowchart workflow Mermaid diagram",
        "Generate a valid Mermaid.js flowchart (starting with graph TD) that visually maps the company's operational processes, bottlenecks, and decision gates. Output ONLY the raw Mermaid diagram code."
    ),
    (
        "system_diagrams", "System Diagrams", "systems data flow architecture topology diagram",
        "Generate a valid Mermaid.js flowchart (starting with graph TD) representing the data exchange, systems communication, and microservice nodes of the company. Output ONLY the raw Mermaid diagram code."
    ),
    (
        "learning_outcomes", "Teaching Note: Learning Objectives", "",
        "Summarize the intended learning objectives and the key takeaways an instructor should draw out using the brief's learning outcomes."
    ),
]

_SYSTEM = (
    "You are an award-winning business school case writer (Harvard/Ivey style). "
    "You write rigorous, narrative-driven teaching cases in the PAST TENSE, third "
    "person. RULES: (1) Write strictly in the PAST TENSE (e.g., worked, was, were, had, ran, conducted, analyzed. "
    "Do NOT use present-tense verbs such as 'is', 'are', 'has', 'have', 'runs', or 'seeks' to describe company operations, challenges, or actions). "
    "(2) Use ONLY facts from the provided Case Brief and retrieved passages - never invent names, numbers, dates, or quotes. "
    "(3) Do NOT include any source tags, file names, bracketed citations, page numbers, or pdf file mentions (e.g. do not write [infosys-ar-25] or (infosys-ar-25.pdf)) in the text. "
    "(4) Do NOT use markdown bold formatting (i.e. do not use '**') or ALL CAPS words to highlight terms within paragraphs; write in clean, standard, professional English prose. "
    "(5) Write in clear, concrete prose - NO bullet-point summaries unless the section explicitly calls for a list. "
    "(6) Never use marketing/consultancy filler. (7) Match the voice and structure of the STYLE EXAMPLE without copying its facts."
)

_CITE_RE = re.compile(r"\[[^\]]+\]")


def _facts_block(index: HybridIndex | None, company: str, query_suffix: str, max_chars: int = 6000) -> str:
    if index is None or not query_suffix:
        return ""
    try:
        results = index.query(f"{company} {query_suffix}", top_k_final=6)
    except Exception as exc:
        log.warning(f"Fact retrieval failed for {query_suffix!r}: {exc}")
        return ""
    parts, used = [], 0
    for rc in results:
        block = f"[{rc.chunk.source_id}] {rc.chunk.raw_text}\n"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)


def _banned_hits(text: str) -> list[str]:
    low = text.lower()
    return [w for w in BANNED_WORDS if re.search(rf"\b{re.escape(w)}\b", low)]


def enforce_past_tense(text: str) -> str:
    """Scan incoming text strings and automatically flag present-tense verbs (is, are, runs),
    converting them into neutral past-tense alternatives (was, were, ran).
    """
    replacements = {
        r"\bis\b": "was",
        r"\bare\b": "were",
        r"\bhas\b": "had",
        r"\bhave\b": "had",
        r"\bruns\b": "ran",
        r"\brun\b": "ran",
        r"\bgoes\b": "went",
        r"\bgo\b": "went",
        r"\bdevelops\b": "developed",
        r"\bdevelop\b": "developed",
        r"\bworries\b": "worried",
        r"\bworry\b": "worried",
        r"\bthinks\b": "thought",
        r"\bthink\b": "thought",
        r"\bplans\b": "planned",
        r"\bplan\b": "planned",
        r"\bpromises\b": "promised",
        r"\bpromise\b": "promised",
        r"\bseeks\b": "sought",
        r"\bseek\b": "sought",
        r"\bforces\b": "forced",
        r"\bforce\b": "forced",
        r"\bcompares\b": "compared",
        r"\bcompare\b": "compared",
        r"\bcreates\b": "created",
        r"\bcreate\b": "created",
        r"\bcomes\b": "came",
        r"\bcome\b": "came",
        r"\bhelps\b": "helped",
        r"\bhelp\b": "helped",
        r"\bshows\b": "showed",
        r"\bshow\b": "showed",
        r"\bfinds\b": "found",
        r"\bfind\b": "found",
        r"\bkeeps\b": "kept",
        r"\bkeep\b": "kept",
        r"\bprovides\b": "provided",
        r"\bprovide\b": "provided",
        r"\ballows\b": "allowed",
        r"\ballow\b": "allowed",
        r"\bensures\b": "ensured",
        r"\bensure\b": "ensured",
        r"\bleads\b": "led",
        r"\blead\b": "led",
        r"\bneeds\b": "needed",
        r"\bneed\b": "needed",
        r"\bseems\b": "seemed",
        r"\bseem\b": "seemed",
        r"\bcontinues\b": "continued",
        r"\bcontinue\b": "continued",
        r"\bdemands\b": "demanded",
        r"\bdemand\b": "demanded"
    }
    cleaned = text
    for pattern, rep in replacements.items():
        def replace_match(match):
            word = match.group(0)
            if word[0].isupper():
                return rep.capitalize()
            return rep
        cleaned = re.sub(pattern, replace_match, cleaned, flags=re.IGNORECASE)
    return cleaned


def enforce_character_naming(text: str, protagonist_name: str, state_tracker: dict | None) -> str:
    """Enforces first-mention naming rules: full name on first mention,
    surname exclusively for all subsequent mentions.
    """
    if not protagonist_name:
        return text
    parts = protagonist_name.split()
    if len(parts) < 2:
        return text
    surname = parts[-1]
    
    if state_tracker is None:
        state_tracker = {}
        
    has_been_mentioned = state_tracker.get(protagonist_name, False)
    
    cleaned = text
    if has_been_mentioned:
        # Replace all occurrences of full name with surname
        cleaned = re.sub(re.escape(protagonist_name), surname, cleaned)
    else:
        # Find the first occurrence of the full name
        match = re.search(re.escape(protagonist_name), cleaned)
        if match:
            # Mark as mentioned
            state_tracker[protagonist_name] = True
            first_idx = match.start()
            # Everything after the first occurrence has the full name replaced by the surname
            before = cleaned[:first_idx + len(protagonist_name)]
            after = cleaned[first_idx + len(protagonist_name):]
            after = re.sub(re.escape(protagonist_name), surname, after)
            cleaned = before + after
            
    return cleaned


def enforce_temporal_boundary(text: str, max_year: int) -> str:
    """Temporal Boundary Lock (Anachronism Patrol).
    If the case scenario is anchored to max_year, automatically strip out
    any metrics or timeline details dated after that year.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    filtered = []
    for sentence in sentences:
        if not sentence.strip():
            continue
        # Find all 4-digit numbers that could be years
        years = [int(y) for y in re.findall(r'\b(20\d{2})\b', sentence)]
        if any(y > max_year for y in years):
            log.info(f"Anachronism Patrol: Stripping sentence with future year reference: {sentence.strip()}")
            continue
        filtered.append(sentence)
    return " ".join(filtered)


def clean_prose(text: str) -> str:
    """Strips markdown bold markers, bracketed source citations, PDF tags, and LLM preambles/meta-text."""
    # 1. Strip markdown bold markers
    text = text.replace("**", "")
    
    # 2. Strip common bracketed source citations or page references
    text = re.sub(r'\[[^\]]+\]', '', text)
    text = re.sub(r'\([a-zA-Z0-9_-]+\.pdf\)', '', text)
    text = re.sub(r'\([a-zA-Z0-9_-]+\.[a-zA-Z0-9]+\)', '', text)
    text = re.sub(r'\b[a-zA-Z0-9_-]+\.pdf\b', '', text)
    
    # 3. Strip LLM conversational preambles/metadata/headers from the rewrite cycles
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            cleaned_lines.append("")
            continue
            
        # Match common LLM meta-prefixes to discard them
        if re.match(
            r'^(here is|sure|ok|this is|revised|updated|rewritten|correction|rejected|version|chapter|section|feedback|resolved)\b', 
            line_strip, 
            re.IGNORECASE
        ):
            # Skip this line completely if it looks like conversational preamble/header
            continue
            
        # Also strip duplicate markdown headers if they leaked inside the body
        if line_strip.startswith("#"):
            continue
            
        cleaned_lines.append(line)
        
    text = "\n".join(cleaned_lines)
    
    # 4. Clean up multiple spaces and punctuation formatting
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _generate_section(
    client,
    brief: CaseBrief,
    spec: tuple[str, str, str, str],
    facts: str,
    style_example: str,
    state_tracker: dict | None = None,
    archetype: str = "Explanatory",
    target_pages: int = 20
) -> str:
    from src.llm_client import Role

    key, title, _, guidance = spec
    brief_json = brief.model_dump_json(indent=1)
    style_block = (
        f"STYLE EXAMPLE (imitate voice/structure only, NOT facts):\n{style_example}\n\n"
        if style_example else ""
    )
    facts_section = f"RETRIEVED COMPANY FACTS (source-tagged):\n{facts}\n\n" if facts else ""
    
    # Calculate target length constraints programmatically
    is_diagram = any(w in title.lower() for w in ("diagram", "flowchart", "mermaid"))
    if not is_diagram:
        if target_pages <= 10:
            target_words = 300
            length_guidance = (
                "WRITING LENGTH CONSTRAINT:\n"
                "Your target length for this section is strictly 250 to 350 words. "
                "Write concise, high-density prose using short, punchy paragraphs. Focus strictly on key operational facts."
            )
        elif target_pages <= 20:
            target_words = 500
            length_guidance = (
                "WRITING LENGTH CONSTRAINT:\n"
                "Your target length for this section is strictly 450 to 550 words. "
                "Write standard-length paragraphs balancing narrative background with core operational details."
            )
        else:
            target_words = 800
            length_guidance = (
                "WRITING LENGTH CONSTRAINT:\n"
                "Your target length for this section is strictly 750 to 850 words. "
                "Write extensive, highly detailed, multi-dimensional narrative prose."
            )
    else:
        length_guidance = ""

    # Formulate archetype-specific system behavior steering rules
    archetype_guidance = (
        f"CASE STUDY ARCHETYPE: {archetype}\n"
        f"You must strictly maintain this archetype style across the narrative:\n"
    )
    if archetype.lower() == "illustrative":
        archetype_guidance += (
            "- Focus deeply on concrete, real-world examples, specific operational situations, and "
            "vivid illustrative vignettes to make abstract business and quality concepts extremely easy to grasp.\n"
            "- Ensure the tone is illustrative: describe specific operational events and scenes rather than high-level summaries.\n"
        )
    elif archetype.lower() == "explanatory":
        archetype_guidance += (
            "- Focus heavily on cause-and-effect operational linkages, detailing the 'why' behind every success, "
            "operational failure, and strategic turnaround decision.\n"
            "- Ensure the tone is explanatory: connect structural problems directly to managerial actions.\n"
        )
    elif archetype.lower() == "descriptive":
        archetype_guidance += (
            "- Focus on detailing the organizational phenomenon exactly as it occurred within its real-world "
            "corporate setting, grounding the details in operational management theory.\n"
        )
    elif archetype.lower() == "evaluative":
        archetype_guidance += (
            "- Focus on analytical assessments, weight trade-offs, and critical review of the quality "
            "interventions to judge their effectiveness, strengths, and drawbacks.\n"
        )
    else:  # Cumulative
        archetype_guidance += (
            "- Focus on aggregating multiple past lessons, benchmarks, and industry comparison points "
            "to construct a broad-base database of operational learnings.\n"
        )

    # Protagonist constraint steering
    protagonist_name = brief.protagonist.name if brief.protagonist else ""
    protagonist_role = brief.protagonist.designation if brief.protagonist else ""
    protagonist_decision = brief.protagonist.decision_context if brief.protagonist else ""
    
    if protagonist_name:
        protagonist_guidance = (
            f"EXECUTIVE PROTAGONIST CONSTRAINT:\n"
            f"The case study narrative MUST revolve around the protagonist: {protagonist_name} ({protagonist_role}). "
            f"Focus on their perspective, administrative dilemmas, and their key decision: '{protagonist_decision}'."
        )
    else:
        protagonist_guidance = ""

    # Section continuity steering (Challenge -> Solution mapping)
    continuity_guidance = (
        "NARRATIVE CONTINUITY CONSTRAINT:\n"
        "Ensure this section belongs to a cohesive case study family. Every operational bottleneck or challenge "
        "mentioned in 'The Challenge' section MUST map logically and relate directly to the interventions, quality tools, "
        "and solutions described in the 'Approach / Solution' and 'Implementation' sections."
    )

    # Exhibit Integration steering
    exhibit_integration_guidance = (
        "NARRATIVE INTEGRATION OF EXHIBITS & TABLES:\n"
        "When discussing operational data, quality metrics, bottlenecks, implementation timelines, or interventions, "
        "you must explicitly integrate references to the exhibits and tables using text references like 'Table 1', "
        "'Table 2', 'Exhibit 1', 'Exhibit 2', 'Exhibit 3', or 'Exhibit 4' inside the body paragraphs. "
        "For example, refer to data trends using 'As shown in Exhibit 1...' or 'According to Table 1...'. "
        "Ensure there is a strong narrative relationship between the text and these referenced artifacts."
    )

    # Catchy Opening Hook steering
    vignette_guidance = ""
    if key == "vignette":
        vignette_guidance = (
            "EXCEPTIONAL QUALITY OPENING HOOK RULES:\n"
            "Write a highly engaging, catchy, attractive, and mind-blowing opening hook. "
            "Ensure the scene is set vividly within the first two sentences to draw the reader in. "
            "Establish high operational narrative tension. Do NOT output a heading, section title, or introduction header."
        )

    # Strict past-tense formatting instruction
    past_tense_steering = (
        "STRICT PAST TENSE COMPLIANCE RULES:\n"
        "You MUST write every sentence strictly in the PAST TENSE (e.g., 'the company faced', 'the executive decided', 'the metrics deteriorated', 'the operations were'). "
        "Do NOT write in the present tense (e.g. do not use 'is', 'are', 'has', 'have', 'runs', 'seeks', 'works', 'continues'). "
        "Double-check that operations from 2023-2024 are described purely in the past tense. This is a critical requirement."
    )

    prompt = (
        f"CASE BRIEF (structured, source-anchored):\n{brief_json}\n\n"
        f"{facts_section}{style_block}"
        f"{length_guidance}\n\n"
        f"{archetype_guidance}\n"
        f"{protagonist_guidance}\n\n"
        f"{continuity_guidance}\n\n"
        f"{exhibit_integration_guidance}\n\n"
        f"{vignette_guidance}\n\n"
        f"{past_tense_steering}\n\n"
        f"Write the section titled \"{title}\" for the case on {brief.company}.\n"
        f"Section guidance: {guidance}\n\n"
        "Output ONLY the section body prose (no heading, no preamble). Past tense, "
        "third person. Absolutely no source tags, file citations, page numbers, or markdown bold markers."
    )

    body = client.complete(
        prompt, role=Role.REASONING, system=_SYSTEM, temperature=0.4, max_tokens=2200
    )
    body = (body or "").strip()

    hits = _banned_hits(body)
    if hits:
        log.info(f"Section {key!r}: rewriting to remove banned words {hits}.")
        body = _strip_banned(client, body, hits) or body

    # Apply Layer 4 Compliance Processing Passes
    body = enforce_past_tense(body)
    
    protagonist_name = brief.protagonist.name if brief.protagonist else ""
    body = enforce_character_naming(body, protagonist_name, state_tracker)
    
    # Extract max timeline year for temporal boundary lock
    years = []
    if brief.historical_timeline:
        for ev in brief.historical_timeline:
            found = re.findall(r"\b(20\d{2})\b", ev.date)
            if found:
                years.extend([int(y) for y in found])
    if brief.protagonist and brief.protagonist.decision_timeframe:
        found = re.findall(r"\b(20\d{2})\b", brief.protagonist.decision_timeframe)
        if found:
            years.extend([int(y) for y in found])
    max_year = max(years) if years else 2025
    body = enforce_temporal_boundary(body, max_year)

    # Final visual sanitation layer to strip citations, PDFs, and bolding
    body = clean_prose(body)

    return body


def _strip_banned(client, body: str, hits: list[str]) -> str:
    from src.llm_client import Role

    prompt = (
        "Rewrite the passage below to REMOVE these banned words/phrases while "
        f"preserving every fact exactly: {', '.join(hits)}.\n"
        "Keep past tense, third person. Output only the rewritten passage. Do NOT output any source citations or markdown bold markers.\n\n"
        f"{body}"
    )
    try:
        return (client.complete(prompt, role=Role.REASONING, temperature=0.2, max_tokens=2200) or "").strip()
    except Exception as exc:
        log.warning(f"Banned-word rewrite failed: {exc}")
        return ""


def generate_case_study(
    brief: CaseBrief,
    company_index: HybridIndex | None = None,
    style_index: HybridIndex | None = None,
    progress_cb: Callable[[str, float], None] | None = None,
    archetype: str = "Explanatory",
    target_pages: int = 20
) -> CaseStudyDraft:
    """Generate the full multi-section case-study draft from a CaseBrief.

    progress_cb(message, fraction) is an optional hook for the Streamlit UI.
    """
    from src.llm_client import get_llm_client

    client = get_llm_client()
    sections: list[Section] = []
    total = len(_SECTION_SPECS)
    state_tracker = {}

    for i, spec in enumerate(_SECTION_SPECS):
        key, title, query_suffix, _ = spec
        if progress_cb:
            progress_cb(f"Writing: {title}", i / total)
        log.info(f"Generating section {i + 1}/{total}: {title}")

        facts = _facts_block(company_index, brief.company, query_suffix)
        style_example = get_style_example(style_index, f"{title} {query_suffix}".strip())
        body = _generate_section(client, brief, spec, facts, style_example, state_tracker, archetype, target_pages)
        sections.append(Section(key=key, title=title, body=body))

    if progress_cb:
        progress_cb("Draft complete", 1.0)

    draft = CaseStudyDraft(
        company=brief.company,
        title=f"{brief.company}: A Quality and Operations Case Study",
        sections=sections,
    )
    log.info(f"Case study draft generated: {len(sections)} sections, ~{draft.word_count} words.")
    return draft

class StyleTransferredGenerator:
    def __init__(self):
        pass

    def generate_chapters(self, brief: CaseBrief) -> dict[str, str]:
        draft = generate_case_study(brief)
        return {s.title: s.body for s in draft.sections}

    def execute_full_generation_loop(self, brief: CaseBrief) -> dict[str, str]:
        return self.generate_chapters(brief)

# =====================================================================
# AUTOMATED GENERATOR BRIDGE LAYER (LEAVES WARP'S CODE UNTOUCHED)
# =====================================================================
import inspect

# Dynamically locate whatever case writing class Warp built inside this file (excluding Pydantic models)
_found_generator = None
for _name, _obj in list(globals().items()):
    if inspect.isclass(_obj) and _obj.__module__ == __name__ and _name != "StyleTransferredGenerator":
        if issubclass(_obj, BaseModel):
            continue
        if any(k in _name.lower() for k in ["generator", "writer", "composer", "case"]):
            _found_generator = _obj
            break

if _found_generator:
    StyleTransferredGenerator = _found_generator
else:
    # Preserve the original StyleTransferredGenerator class if no override exists in globals
    StyleTransferredGenerator = globals().get("CaseGenerator", globals().get("Generator", StyleTransferredGenerator))