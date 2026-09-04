"""``job_retrieval`` -- union the RAG vector-search hits for the user's query
with a recency page of their own job corpus, capped at eight job ids.
"""

from typing import TYPE_CHECKING, Any

from app.domain.agents.state import ManaState
from app.domain.agents.tools.registry import TOOL_SPECS, call_tool
from app.domain.agents.tools.vector_search import vector_search
from app.domain.jobs.service import JobFilters, JobService

if TYPE_CHECKING:
    from app.domain.agents.graph import AgentDeps


async def job_retrieval(state: ManaState, *, deps: "AgentDeps") -> dict[str, Any]:
    query = (state["inputs"].get("query") or "").strip() or "roles matching my background"

    hits, _ = await call_tool(
        state,
        TOOL_SPECS["vector_search"],
        {
            "session": deps.session,
            "embeddings": deps.embeddings,
            "query": query,
            "user_id": deps.user_id,
            "k": 12,
        },
        vector_search,
    )

    job_ids: list[str] = []
    for hit in hits:
        job_id = str(hit["ref_id"]).split(":", 1)[0]
        if job_id and job_id not in job_ids:
            job_ids.append(job_id)

    if len(job_ids) < 5:
        jobs, _ = await JobService(deps.session).list_(
            deps.user_id, JobFilters(sort="recent", limit=12)
        )
        for job in jobs:
            jid = str(job.id)
            if jid not in job_ids:
                job_ids.append(jid)

    retrieved = job_ids[:8]

    await deps.svc._log_action(
        user_id=deps.user_id,
        session_id=deps.session_id,
        run_id=deps.run_id,
        node="job_retrieval",
        action_key="searched_corpus",
        summary=f"Searched your job corpus — {len(retrieved)} roles",
    )

    return {
        "retrieved_jobs": retrieved,
        "_summary": f"Found {len(retrieved)} candidate roles",
        "_detail": {"count": len(retrieved)},
    }
