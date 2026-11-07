"""What the API routes share: settings, the search stack (built on first use), the model
client (built on first use, so the server starts without a key), and the extraction jobs.
"""

import threading
from collections.abc import Callable

from fastapi import HTTPException, Request

from rfp_intel.agents.graph import run_extraction
from rfp_intel.agents.llm import LLM, LLMError, llm_from_settings
from rfp_intel.agents.services import Services
from rfp_intel.api.jobs import Jobs, JobStore
from rfp_intel.api.schemas import Job
from rfp_intel.config import Settings
from rfp_intel.logs import get_logger
from rfp_intel.search.runtime import Runtime

log = get_logger(__name__)
RuntimeFactory = Callable[[Settings], Runtime]


class AppContext:
    def __init__(self, settings: Settings, factory: RuntimeFactory, llm: LLM | None) -> None:
        self.settings = settings
        self.factory = factory
        self.jobs = Jobs(JobStore(settings.db_path))
        self._lock = threading.Lock()
        self._runtime: Runtime | None = None
        self._llm = llm

    def runtime(self) -> Runtime:
        with self._lock:
            if self._runtime is None:
                self._runtime = self.factory(self.settings)
            return self._runtime

    def reranker_loaded(self) -> bool | None:
        """Whether the cross-encoder is loaded; None before the search stack is first used."""
        return None if self._runtime is None else self._runtime.reranker is not None

    def llm(self) -> LLM:
        """The model client, or HTTP 503 naming the missing setting."""
        with self._lock:
            if self._llm is None:
                try:
                    self._llm = llm_from_settings(self.settings)
                except LLMError as exc:
                    raise HTTPException(status_code=503, detail=str(exc)) from exc
            return self._llm

    def services(self) -> Services:
        """Fresh per run: a run owns its root span and evidence store."""
        return Services.build(self.settings, self.runtime(), self.llm(), self.settings.outputs_dir)

    def start_extraction(self, bid_id: str) -> Job:
        services = self.services()  # fail fast (503) when no model is configured

        def work(job: Job) -> None:
            result, _ = run_extraction(services, bid_id, run_id=job.run_id)
            job.validation = result.validation

        return self.jobs.submit(bid_id, work)

    def close(self) -> None:
        self.jobs.shutdown()
        if self._runtime is not None:
            self._runtime.close()
            self._runtime = None


def context(request: Request) -> AppContext:
    ctx: AppContext = request.app.state.context
    return ctx
