"""Job orchestrator.

Runs the pipeline stages for a project sequentially in a worker thread (stages are
blocking: ffmpeg, COLMAP, training). Stage status is persisted to metadata.json after
every transition, so a crashed or cancelled job resumes from the first incomplete
stage. Progress events stream to the UI through the event bus → WebSocket.
"""

from __future__ import annotations

import threading
import time
import traceback

from .config import settings
from .events import bus
from .models import JobState, StageName, StageState, StageStatus, utcnow
from .pipeline.base import PipelineStage, StageCancelled, StageContext, StageError
from .pipeline.extract import ExtractFramesStage
from .pipeline.filter import FilterFramesStage
from .pipeline.optimize import OptimizeStage
from .pipeline.poses import EstimatePosesStage
from .pipeline.preview import PreviewStage
from .pipeline.train import TrainStage
from .pipeline.validate import ValidateStage
from .plugins import extra_stages
from .projects import ProjectStore, store

# Rough share of total runtime per stage, used for the ETA estimate.
STAGE_WEIGHTS: dict[StageName, float] = {
    StageName.preparing: 0.02,
    StageName.extracting_frames: 0.06,
    StageName.filtering_frames: 0.02,
    StageName.estimating_poses: 0.25,
    StageName.training: 0.60,
    StageName.optimizing: 0.01,
    StageName.generating_preview: 0.04,
}


def build_stages() -> list[PipelineStage]:
    stages: list[PipelineStage] = [
        ValidateStage(),
        ExtractFramesStage(),
        FilterFramesStage(),
        EstimatePosesStage(),
        TrainStage(),
        OptimizeStage(),
        PreviewStage(),
    ]
    return extra_stages(stages)


class JobRunner:
    def __init__(self, project_store: ProjectStore | None = None) -> None:
        self.store = project_store or store
        self._threads: dict[str, threading.Thread] = {}
        self._cancels: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ control

    def start(self, project_id: str, *, resume: bool = True, retrain: bool = False) -> JobState:
        with self._lock:
            if self.is_running(project_id):
                raise StageError("A job is already running for this project.")
            meta = self.store.load(project_id)
            stages = build_stages()

            if retrain:
                self._clear_training_outputs(project_id)
            previous = meta.job if (resume and meta.job and not retrain) else None
            job = JobState(
                project_id=project_id,
                status=StageStatus.running,
                started_at=utcnow(),
                stages=[self._carry_over(s, previous) for s in stages],
            )
            meta.job = job
            self.store.save(meta)

            cancel = threading.Event()
            self._cancels[project_id] = cancel
            t = threading.Thread(target=self._run, args=(project_id, stages, cancel), daemon=True)
            self._threads[project_id] = t
            t.start()
            return job

    def cancel(self, project_id: str) -> None:
        ev = self._cancels.get(project_id)
        if ev:
            ev.set()

    def is_running(self, project_id: str) -> bool:
        t = self._threads.get(project_id)
        return bool(t and t.is_alive())

    @staticmethod
    def _carry_over(stage: PipelineStage, previous: JobState | None) -> StageState:
        if previous:
            for old in previous.stages:
                if old.name == stage.name and old.status == StageStatus.completed:
                    return old
        return StageState(name=stage.name)

    def _clear_training_outputs(self, project_id: str) -> None:
        import shutil

        p = self.store.path(project_id)
        for sub in ("splat", "preview"):
            d = p / sub
            if d.exists():
                shutil.rmtree(d)
            d.mkdir()

    # ------------------------------------------------------------------ execution

    def _run(self, project_id: str, stages: list[PipelineStage], cancel: threading.Event) -> None:
        meta = self.store.load(project_id)
        job = meta.job
        assert job is not None
        project_dir = self.store.path(project_id)
        t0 = time.monotonic()
        accumulated: dict[str, object] = {}

        def persist() -> None:
            job.elapsed_s = round(time.monotonic() - t0, 1)
            self.store.save(meta)

        last_persist = [0.0]

        def emit(stage_state: StageState) -> None:
            job.current_stage = stage_state.name
            job.eta_s = self._estimate_eta(job, t0)
            bus.publish_threadsafe(project_id, {
                "type": "progress",
                "job": job.model_dump(mode="json"),
            })
            # Throttled persistence: long stages (training runs for hours) otherwise leave
            # metadata.json frozen at 0%, so polling clients, app reopen and the library
            # thumbnails all look stalled. Persist at most every 3s during a stage.
            now = time.monotonic()
            if now - last_persist[0] >= 3.0:
                last_persist[0] = now
                persist()

        try:
            for stage, state in zip(stages, job.stages):
                if state.status == StageStatus.completed:
                    accumulated.update(state.outputs)
                    continue
                ctx = StageContext(
                    project_id=project_id,
                    project_dir=project_dir,
                    config=meta.config,
                    cancel_event=cancel,
                    report_progress=lambda p, msg, s=state: self._on_progress(s, p, msg, emit),
                    outputs=accumulated,
                )
                state.status = StageStatus.running
                state.started_at = utcnow()
                state.error = None
                persist()
                emit(state)

                if stage.should_skip(ctx):
                    state.status = StageStatus.skipped
                    state.progress = 1.0
                    state.message = "Reused previous result"
                else:
                    outputs = stage.run(ctx)
                    state.outputs = outputs or {}
                    accumulated.update(state.outputs)
                    state.status = StageStatus.completed
                    state.progress = 1.0
                state.finished_at = utcnow()
                persist()
                emit(state)
                cancelled_or_running = cancel.is_set()
                if cancelled_or_running:
                    raise StageCancelled()

            job.status = StageStatus.completed
            job.current_stage = StageName.completed
            job.finished_at = utcnow()
            meta.stats.update(self._collect_stats(job))
            if settings.auto_delete_intermediates:
                self._delete_intermediates(project_dir)
            persist()
            bus.publish_threadsafe(project_id, {"type": "completed",
                                                "job": job.model_dump(mode="json")})
        except StageCancelled:
            self._fail(meta, job, "Cancelled by user", cancelled=True)
        except StageError as e:
            self._fail(meta, job, str(e))
        except Exception:
            self._fail(meta, job, "Unexpected error:\n" + traceback.format_exc(limit=8))
        finally:
            self._cancels.pop(project_id, None)
            self._threads.pop(project_id, None)

    def _fail(self, meta, job: JobState, message: str, cancelled: bool = False) -> None:
        job.status = StageStatus.failed
        job.error = message
        job.finished_at = utcnow()
        for s in job.stages:
            if s.status == StageStatus.running:
                s.status = StageStatus.failed
                s.error = message
        self.store.save(meta)
        bus.publish_threadsafe(job.project_id, {
            "type": "cancelled" if cancelled else "failed",
            "job": job.model_dump(mode="json"),
        })

    @staticmethod
    def _on_progress(state: StageState, progress: float, message: str, emit) -> None:
        state.progress = max(0.0, min(1.0, progress))
        state.message = message
        emit(state)

    @staticmethod
    def _estimate_eta(job: JobState, t0: float) -> float | None:
        done_weight = 0.0
        for s in job.stages:
            w = STAGE_WEIGHTS.get(s.name, 0.0)
            if s.status in (StageStatus.completed, StageStatus.skipped):
                done_weight += w
            elif s.status == StageStatus.running:
                done_weight += w * s.progress
        if done_weight < 0.03:
            return None
        elapsed = time.monotonic() - t0
        return round(elapsed * (1.0 - done_weight) / done_weight, 0)

    @staticmethod
    def _collect_stats(job: JobState) -> dict:
        stats: dict = {}
        for s in job.stages:
            stats.update({k: v for k, v in s.outputs.items()
                          if isinstance(v, (int, float, str))})
        return stats

    @staticmethod
    def _delete_intermediates(project_dir) -> None:
        import shutil

        for sub in ("frames_raw", "colmap"):
            d = project_dir / sub
            if d.exists():
                shutil.rmtree(d)


runner = JobRunner()


def recover_interrupted_jobs(project_store: ProjectStore | None = None) -> int:
    """Mark jobs left 'running' by a previous process as failed so they can be resumed.

    Called at startup: any job persisted as running necessarily has no live worker
    thread in this process — the app crashed or was killed mid-run.
    """
    s = project_store or store
    recovered = 0
    for meta in s.list():
        job = meta.job
        if job and job.status == StageStatus.running:
            job.status = StageStatus.failed
            job.error = "Interrupted — the app was closed while the job was running. Press Resume to continue."
            job.finished_at = utcnow()
            for stage in job.stages:
                if stage.status == StageStatus.running:
                    stage.status = StageStatus.failed
                    stage.error = job.error
            s.save(meta)
            recovered += 1
    return recovered
