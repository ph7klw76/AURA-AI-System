"""
AURA local-document ingestion subsystem (Phase 4).

Optional, opt-in pipeline that lets Research Scout and Patent Intelligence
read PDFs / DOCX / TXT / MD files from a user-supplied folder.  Provenance
is preserved at chunk level; the verifier and evidence-pack logic can see
that local documents were used and how good the extraction was.
"""
from .models import (
    DiscoveredFile,
    DiscoverySummary,
    ExtractionQuality,
    ExtractionWarning,
    FolderPreference,
    LocalDocumentChunk,
    LocalDocumentExtraction,
    LocalEvidenceRef,
    LocalIngestionSummary,
    NeedsUserInputRequest,
    PreferenceState,
    SourceType,
)
from .pipeline import ingest_folder
from .retrieval import (
    retrieve_evidence_per_document,
    retrieve_literature_evidence,
    retrieve_literature_evidence_per_document,
    retrieve_local_evidence,
    retrieve_patent_evidence,
    retrieve_patent_evidence_per_document,
)
from .session_preferences import (
    absorb_user_response,
    build_prompt_request,
    clear_session,
    get_preference,
    is_opt_in_enabled,
    needs_prompt,
    new_session_id,
    set_preference,
)

__all__ = [
    # models
    "DiscoveredFile",
    "DiscoverySummary",
    "ExtractionQuality",
    "ExtractionWarning",
    "FolderPreference",
    "LocalDocumentChunk",
    "LocalDocumentExtraction",
    "LocalEvidenceRef",
    "LocalIngestionSummary",
    "NeedsUserInputRequest",
    "PreferenceState",
    "SourceType",
    # session
    "absorb_user_response",
    "build_prompt_request",
    "clear_session",
    "get_preference",
    "is_opt_in_enabled",
    "needs_prompt",
    "new_session_id",
    "set_preference",
    # pipeline + retrieval
    "ingest_folder",
    "retrieve_evidence_per_document",
    "retrieve_literature_evidence",
    "retrieve_literature_evidence_per_document",
    "retrieve_local_evidence",
    "retrieve_patent_evidence",
    "retrieve_patent_evidence_per_document",
]
