from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import get_current_user
from api.schemas import TaskCreate, TaskOut
from store import get_store

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
def list_tasks(user: dict = Depends(get_current_user)):
    store = get_store(user["user_id"])
    return [TaskOut(id=t["id"], task=t["task"], due=t.get("due"), status=t["status"])
            for t in store.open_tasks()]


@router.post("", response_model=list[TaskOut], status_code=status.HTTP_201_CREATED)
def add_task(body: TaskCreate, user: dict = Depends(get_current_user)):
    store = get_store(user["user_id"])
    added = store.add_tasks([{"task": body.task, "due": body.due}])
    return [TaskOut(id=t["id"], task=t["task"], due=t.get("due"), status=t["status"]) for t in added]


@router.post("/{task_id}/complete", response_model=TaskOut)
def complete_task(task_id: str, user: dict = Depends(get_current_user)):
    store = get_store(user["user_id"])
    done = store.complete_task_by_id(task_id)
    if done is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no open task with that id")
    return TaskOut(id=done["id"], task=done["task"], due=done.get("due"), status=done["status"])


@router.post("/{task_id}/reopen", response_model=TaskOut)
def reopen_task(task_id: str, user: dict = Depends(get_current_user)):
    store = get_store(user["user_id"])
    reopened = store.reopen_task(task_id)
    if reopened is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no completed task with that id")
    return TaskOut(id=reopened["id"], task=reopened["task"], due=reopened.get("due"),
                    status=reopened["status"])
