import hashlib
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal, get_scoped, require
from app.core.config import settings
from app.core.errors import AppError, InvalidTransition, NotFound
from app.db.session import get_db
from app.domain.workflow import PROJECT_STAGES, TASK_STATUSES, check_project_stage, project_progress
from app.models import Document, Milestone, Project, Proposal, Task, TaskComment, task_dependencies
from app.models.crm import Activity
from app.rag.parsing import safe_filename
from app.rag.storage import get_storage, object_key
from app.schemas.common import ORM, ActivityOut, Page
from app.services import delivery as delivery_svc
from app.services.common import audit, notify, org_name_map, paginate, record_activity, user_name_map

router = APIRouter(tags=["projects"])


class ProjectOut(ORM):
    id: uuid.UUID
    organisation_id: uuid.UUID
    organisation_name: str | None = None
    proposal_id: uuid.UUID | None
    name: str
    description: str
    stage: str
    status: str
    owner_id: uuid.UUID | None
    owner_name: str | None = None
    start_date: date | None
    target_date: date | None
    progress: int = 0
    tasks_done: int = 0
    tasks_total: int = 0
    created_at: datetime


class ProjectCreate(BaseModel):
    proposal_id: uuid.UUID


class ProjectPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    description: str | None = Field(None, max_length=8000)
    status: str | None = Field(None, pattern="^(active|on_hold|completed)$")
    owner_id: uuid.UUID | None = None
    target_date: date | None = None


class StageIn(BaseModel):
    stage: str


def _task_scope(stmt, principal: Principal):
    return stmt if principal.is_internal else stmt.where(Task.customer_visible.is_(True))


def _project_out(db: Session, p: Project, principal: Principal) -> ProjectOut:
    done, total = db.execute(select(func.count().filter(Task.status == "done"), func.count())
                             .where(Task.project_id == p.id)).one()
    return ProjectOut.model_validate(p).model_copy(update={
        "organisation_name": org_name_map(db, [p.organisation_id]).get(p.organisation_id),
        "owner_name": user_name_map(db, [p.owner_id]).get(p.owner_id),
        "progress": project_progress(p.stage, done, total), "tasks_done": done, "tasks_total": total})


@router.get("/projects/meta")
def projects_meta():
    return {"stages": PROJECT_STAGES, "task_statuses": TASK_STATUSES}


@router.get("/projects", response_model=Page[ProjectOut])
def list_projects(organisation_id: uuid.UUID | None = None, status: str | None = None, stage: str | None = None,
                  q: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                  principal: Principal = Depends(require("project.read")), db: Session = Depends(get_db)):
    stmt = principal.scope_filter(select(Project), Project)
    if organisation_id:
        stmt = stmt.where(Project.organisation_id == organisation_id)
    if status:
        stmt = stmt.where(Project.status == status)
    if stage:
        stmt = stmt.where(Project.stage == stage)
    if q:
        stmt = stmt.where(Project.name.ilike(f"%{q}%"))
    items, total = paginate(db, stmt.order_by(Project.created_at.desc()), page, page_size)
    return Page(items=[_project_out(db, p, principal) for p in items], total=total, page=page, page_size=page_size)


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, request: Request, principal: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)):
    """Manual creation from an accepted proposal (acceptance normally creates the project automatically)."""
    p = get_scoped(db, Proposal, body.proposal_id, principal, "project.write")
    project = delivery_svc.create_project_from_proposal(db, p, principal.id)
    audit(db, principal.id, "project.create", "project", project.id, project.organisation_id, request=request)
    db.commit()
    return _project_out(db, project, principal)


@router.get("/projects/{pid}", response_model=ProjectOut)
def get_project(pid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return _project_out(db, get_scoped(db, Project, pid, principal, "project.read"), principal)


@router.patch("/projects/{pid}", response_model=ProjectOut)
def patch_project(pid: uuid.UUID, body: ProjectPatch, request: Request, principal: Principal = Depends(get_principal),
                  db: Session = Depends(get_db)):
    p = get_scoped(db, Project, pid, principal, "project.write")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(p, k, v)
    audit(db, principal.id, "project.update", "project", p.id, p.organisation_id, changes, request)
    db.commit()
    return _project_out(db, p, principal)


@router.post("/projects/{pid}/stage", response_model=ProjectOut)
def change_stage(pid: uuid.UUID, body: StageIn, request: Request, principal: Principal = Depends(get_principal),
                 db: Session = Depends(get_db)):
    p = get_scoped(db, Project, pid, principal, "project.write")
    check_project_stage(p.stage, body.stage)
    old = p.stage
    p.stage = body.stage
    if body.stage == "handover":
        p.status = "completed"
        delivery_svc.advance_lead(db, p.organisation_id, "completed", principal.id, "project handed over")
    label = body.stage.replace("_", " ").title()
    record_activity(db, p.organisation_id, "project", p.id, "status_change", f"Project moved to {label}",
                    principal.id, {"from": old, "to": body.stage}, customer_visible=True)
    notify(db, p.organisation_id, "project.stage", f"{p.name}: now in {label}", link=f"/portal/projects/{p.id}")
    audit(db, principal.id, "project.stage", "project", p.id, p.organisation_id, {"from": old, "to": body.stage}, request)
    db.commit()
    return _project_out(db, p, principal)


@router.get("/projects/{pid}/timeline")
def project_timeline(pid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    p = get_scoped(db, Project, pid, principal, "project.read")
    ms_q = select(Milestone).where(Milestone.project_id == p.id)
    if not principal.is_internal:
        ms_q = ms_q.where(Milestone.customer_visible.is_(True))
    milestones = db.scalars(ms_q.order_by(Milestone.position)).all()
    aq = select(Activity).where(Activity.organisation_id == p.organisation_id, Activity.entity_id == p.id)
    if not principal.is_internal:
        aq = aq.where(Activity.customer_visible.is_(True))
    acts = db.scalars(aq.order_by(Activity.created_at.desc()).limit(100)).all()
    names = user_name_map(db, [a.actor_id for a in acts])
    return {
        "stages": [{"key": s, "label": s.replace("_", " ").title(),
                    "state": "done" if PROJECT_STAGES.index(s) < PROJECT_STAGES.index(p.stage) else
                    "current" if s == p.stage else "upcoming"} for s in PROJECT_STAGES],
        "milestones": [MilestoneOut.model_validate(m).model_dump(mode="json") for m in milestones],
        "activity": [ActivityOut.model_validate(a).model_copy(update={"actor_name": names.get(a.actor_id)})
                     .model_dump(mode="json") for a in acts],
        "start_date": p.start_date, "target_date": p.target_date,
    }


# ------------------------------------------------------------------ milestones
class MilestoneIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field("", max_length=4000)
    due_date: date | None = None
    status: str = Field("pending", pattern="^(pending|in_progress|done)$")
    customer_visible: bool = True
    position: int | None = None


class MilestoneOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str
    due_date: date | None
    status: str
    position: int
    customer_visible: bool
    completed_at: datetime | None


@router.get("/projects/{pid}/milestones", response_model=list[MilestoneOut])
def list_milestones(pid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    p = get_scoped(db, Project, pid, principal, "project.read")
    q = select(Milestone).where(Milestone.project_id == p.id)
    if not principal.is_internal:
        q = q.where(Milestone.customer_visible.is_(True))
    return db.scalars(q.order_by(Milestone.position)).all()


@router.post("/projects/{pid}/milestones", response_model=MilestoneOut, status_code=201)
def create_milestone(pid: uuid.UUID, body: MilestoneIn, principal: Principal = Depends(get_principal),
                     db: Session = Depends(get_db)):
    p = get_scoped(db, Project, pid, principal, "project.write")
    pos = body.position if body.position is not None else (
        db.scalar(select(func.count()).select_from(Milestone).where(Milestone.project_id == p.id)) or 0)
    m = Milestone(organisation_id=p.organisation_id, project_id=p.id, **body.model_dump(exclude={"position"}), position=pos)
    db.add(m)
    db.commit()
    return m


@router.patch("/milestones/{mid}", response_model=MilestoneOut)
def patch_milestone(mid: uuid.UUID, body: MilestoneIn, principal: Principal = Depends(get_principal),
                    db: Session = Depends(get_db)):
    m = get_scoped(db, Milestone, mid, principal, "project.write")
    was_done = m.status == "done"
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None or k == "due_date":
            setattr(m, k, v)
    if m.status == "done" and not was_done:
        m.completed_at = datetime.now(UTC)
        record_activity(db, m.organisation_id, "project", m.project_id, "system", f"Milestone completed: {m.title}",
                        principal.id, customer_visible=m.customer_visible)
    elif m.status != "done":
        m.completed_at = None
    db.commit()
    return m


@router.delete("/milestones/{mid}", status_code=204)
def delete_milestone(mid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    m = get_scoped(db, Milestone, mid, principal, "project.write")
    db.delete(m)
    db.commit()


# ------------------------------------------------------------------ tasks
class TaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    description: str = Field("", max_length=8000)
    status: str = Field("todo", pattern="^(backlog|todo|in_progress|review|done)$")
    priority: str = Field("medium", pattern="^(low|medium|high|urgent)$")
    assignee_id: uuid.UUID | None = None
    milestone_id: uuid.UUID | None = None
    due_date: date | None = None
    customer_visible: bool = False


class TaskPatch(BaseModel):
    title: str | None = Field(None, min_length=2, max_length=300)
    description: str | None = Field(None, max_length=8000)
    status: str | None = Field(None, pattern="^(backlog|todo|in_progress|review|done)$")
    priority: str | None = Field(None, pattern="^(low|medium|high|urgent)$")
    assignee_id: uuid.UUID | None = None
    milestone_id: uuid.UUID | None = None
    due_date: date | None = None
    position: int | None = None
    customer_visible: bool | None = None


class TaskOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    milestone_id: uuid.UUID | None
    title: str
    description: str
    status: str
    priority: str
    assignee_id: uuid.UUID | None
    assignee_name: str | None = None
    due_date: date | None
    position: int
    customer_visible: bool
    depends_on: list[uuid.UUID] = []
    blocked: bool = False
    comment_count: int = 0
    created_at: datetime
    updated_at: datetime


def _tasks_out(db: Session, tasks: list[Task]) -> list[TaskOut]:
    ids = [t.id for t in tasks]
    deps: dict[uuid.UUID, list[uuid.UUID]] = {}
    if ids:
        for tid, dep in db.execute(select(task_dependencies.c.task_id, task_dependencies.c.depends_on_id)
                                   .where(task_dependencies.c.task_id.in_(ids))).all():
            deps.setdefault(tid, []).append(dep)
    all_dep_ids = {d for v in deps.values() for d in v}
    done = set(db.scalars(select(Task.id).where(Task.id.in_(all_dep_ids), Task.status == "done"))) if all_dep_ids else set()
    counts = dict(db.execute(select(TaskComment.task_id, func.count()).where(TaskComment.task_id.in_(ids))
                             .group_by(TaskComment.task_id)).all()) if ids else {}
    names = user_name_map(db, [t.assignee_id for t in tasks])
    return [TaskOut.model_validate(t).model_copy(update={
        "assignee_name": names.get(t.assignee_id), "depends_on": deps.get(t.id, []),
        "blocked": any(d not in done for d in deps.get(t.id, [])), "comment_count": counts.get(t.id, 0)}) for t in tasks]


@router.get("/projects/{pid}/tasks", response_model=list[TaskOut])
def list_tasks(pid: uuid.UUID, status: str | None = None, assignee_id: uuid.UUID | None = None,
               principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    p = get_scoped(db, Project, pid, principal, "project.read")
    q = _task_scope(select(Task).where(Task.project_id == p.id), principal)
    if status:
        q = q.where(Task.status == status)
    if assignee_id:
        q = q.where(Task.assignee_id == assignee_id)
    return _tasks_out(db, list(db.scalars(q.order_by(Task.status, Task.position, Task.created_at)).all()))


@router.post("/projects/{pid}/tasks", response_model=TaskOut, status_code=201)
def create_task(pid: uuid.UUID, body: TaskIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    p = get_scoped(db, Project, pid, principal, "project.write")
    if body.milestone_id:
        m = db.get(Milestone, body.milestone_id)
        if m is None or m.project_id != p.id:
            raise NotFound("Milestone not found in this project")
    pos = db.scalar(select(func.count()).select_from(Task).where(Task.project_id == p.id, Task.status == body.status)) or 0
    t = Task(organisation_id=p.organisation_id, project_id=p.id, position=pos, **body.model_dump())
    db.add(t)
    db.flush()
    record_activity(db, p.organisation_id, "project", p.id, "system", f"Task created: {t.title}", principal.id)
    db.commit()
    return _tasks_out(db, [t])[0]


@router.patch("/tasks/{tid}", response_model=TaskOut)
def patch_task(tid: uuid.UUID, body: TaskPatch, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    t = get_scoped(db, Task, tid, principal, "project.write")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("status") == "done" and t.status != "done":
        blockers = db.scalars(select(Task.title).join(task_dependencies, task_dependencies.c.depends_on_id == Task.id)
                              .where(task_dependencies.c.task_id == t.id, Task.status != "done")).all()
        if blockers:
            raise InvalidTransition("Task is blocked by unfinished dependencies", details={"blocked_by": list(blockers)})
    old_status = t.status
    for k, v in changes.items():
        setattr(t, k, v)
    if "status" in changes and changes["status"] != old_status:
        record_activity(db, t.organisation_id, "project", t.project_id, "status_change",
                        f"Task '{t.title}' {old_status} → {t.status}", principal.id,
                        customer_visible=t.customer_visible and t.status == "done")
    db.commit()
    return _tasks_out(db, [t])[0]


@router.delete("/tasks/{tid}", status_code=204)
def delete_task(tid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    t = get_scoped(db, Task, tid, principal, "project.write")
    db.delete(t)
    db.commit()


class DependencyIn(BaseModel):
    depends_on_id: uuid.UUID


def _creates_cycle(db: Session, task_id: uuid.UUID, depends_on: uuid.UUID) -> bool:
    frontier, seen = [depends_on], set()
    while frontier:
        cur = frontier.pop()
        if cur == task_id:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        frontier.extend(db.scalars(select(task_dependencies.c.depends_on_id).where(task_dependencies.c.task_id == cur)))
    return False


@router.post("/tasks/{tid}/dependencies", response_model=TaskOut, status_code=201)
def add_dependency(tid: uuid.UUID, body: DependencyIn, principal: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)):
    t = get_scoped(db, Task, tid, principal, "project.write")
    dep = get_scoped(db, Task, body.depends_on_id, principal)
    if dep.project_id != t.project_id:
        raise AppError("Dependencies must be within the same project", code="invalid_dependency")
    if _creates_cycle(db, t.id, dep.id):
        raise AppError("This dependency would create a cycle", code="dependency_cycle")
    exists = db.scalar(select(func.count()).select_from(task_dependencies).where(
        task_dependencies.c.task_id == t.id, task_dependencies.c.depends_on_id == dep.id))
    if not exists:
        db.execute(insert(task_dependencies).values(task_id=t.id, depends_on_id=dep.id))
    db.commit()
    return _tasks_out(db, [t])[0]


@router.delete("/tasks/{tid}/dependencies/{dep_id}", status_code=204)
def remove_dependency(tid: uuid.UUID, dep_id: uuid.UUID, principal: Principal = Depends(get_principal),
                      db: Session = Depends(get_db)):
    t = get_scoped(db, Task, tid, principal, "project.write")
    db.execute(delete(task_dependencies).where(task_dependencies.c.task_id == t.id,
                                               task_dependencies.c.depends_on_id == dep_id))
    db.commit()


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    internal: bool = True


class CommentOut(ORM):
    id: uuid.UUID
    author_id: uuid.UUID | None
    author_name: str | None = None
    body: str
    internal: bool
    created_at: datetime


@router.get("/tasks/{tid}/comments", response_model=list[CommentOut])
def list_task_comments(tid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    t = get_scoped(db, Task, tid, principal, "project.read")
    if not principal.is_internal and not t.customer_visible:
        raise NotFound("Task not found")
    q = select(TaskComment).where(TaskComment.task_id == t.id)
    if not principal.is_internal:
        q = q.where(TaskComment.internal.is_(False))
    rows = db.scalars(q.order_by(TaskComment.created_at)).all()
    names = user_name_map(db, [r.author_id for r in rows])
    return [CommentOut.model_validate(r).model_copy(update={"author_name": names.get(r.author_id)}) for r in rows]


@router.post("/tasks/{tid}/comments", response_model=CommentOut, status_code=201)
def add_task_comment(tid: uuid.UUID, body: CommentIn, principal: Principal = Depends(get_principal),
                     db: Session = Depends(get_db)):
    t = get_scoped(db, Task, tid, principal, "project.write")
    c = TaskComment(organisation_id=t.organisation_id, task_id=t.id, author_id=principal.id, body=body.body,
                    internal=body.internal)
    db.add(c)
    db.commit()
    return CommentOut.model_validate(c).model_copy(update={"author_name": principal.user.full_name})


class AttachmentOut(ORM):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    uploaded_by: uuid.UUID | None
    created_at: datetime


ATTACHMENT_TYPES = {"application/pdf", "text/plain", "text/markdown", "image/png", "image/jpeg", "text/csv",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
MAGIC = {"application/pdf": b"%PDF-", "image/png": b"\x89PNG", "image/jpeg": b"\xff\xd8\xff"}


@router.get("/tasks/{tid}/attachments", response_model=list[AttachmentOut])
def list_attachments(tid: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    t = get_scoped(db, Task, tid, principal, "project.read")
    if not principal.is_internal and not t.customer_visible:
        raise NotFound("Task not found")
    return db.scalars(select(Document).where(Document.task_id == t.id, Document.kind == "attachment")).all()


@router.post("/tasks/{tid}/attachments", response_model=AttachmentOut, status_code=201)
async def upload_attachment(tid: uuid.UUID, file: UploadFile = File(...), principal: Principal = Depends(get_principal),
                            db: Session = Depends(get_db)):
    t = get_scoped(db, Task, tid, principal, "project.write")
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise AppError(f"File exceeds {settings.max_upload_mb} MB", code="file_too_large")
    ctype = (file.content_type or "").split(";")[0]
    if ctype not in ATTACHMENT_TYPES or (ctype in MAGIC and not data.startswith(MAGIC[ctype])):
        raise AppError("File type not allowed or content does not match its type", code="unsupported_file")
    name = safe_filename(file.filename or "attachment")
    key = object_key(t.organisation_id, name)
    get_storage().put(key, data)
    d = Document(organisation_id=t.organisation_id, project_id=t.project_id, task_id=t.id, kind="attachment",
                 filename=name, title=name, content_type=ctype, size_bytes=len(data),
                 sha256=hashlib.sha256(data).hexdigest(), storage_key=key, status="ready", uploaded_by=principal.id,
                 visibility="organisation" if t.customer_visible else "internal")
    db.add(d)
    db.commit()
    return d


@router.get("/attachments/{did}/download")
def download_attachment(did: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    d = get_scoped(db, Document, did, principal, "project.read")
    if d.kind != "attachment" or (not principal.is_internal and d.visibility != "organisation"):
        raise NotFound("Attachment not found")
    return Response(get_storage().get(d.storage_key), media_type=d.content_type,
                    headers={"Content-Disposition": f'attachment; filename="{d.filename}"',
                             "X-Content-Type-Options": "nosniff"})
