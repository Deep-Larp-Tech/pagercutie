import uuid

from fastapi import APIRouter, status

from pagercutie.core.deps import PaginationDep, SessionDep
from pagercutie.core.schemas import error_responses
from pagercutie.persons import service
from pagercutie.persons.schemas import PersonCreate, PersonRead, PersonUpdate

router = APIRouter(prefix="/persons", tags=["persons"])


@router.get("")
async def list_persons(session: SessionDep, pagination: PaginationDep) -> list[PersonRead]:
    return await service.list_persons(session, pagination)


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(400, 409))
async def create_person(data: PersonCreate, session: SessionDep) -> PersonRead:
    return await service.create_person(session, data)


@router.get("/{person_id}", responses=error_responses(404))
async def get_person(person_id: uuid.UUID, session: SessionDep) -> PersonRead:
    return await service.get_person(session, person_id)


@router.patch("/{person_id}", responses=error_responses(400, 404, 409))
async def update_person(person_id: uuid.UUID, data: PersonUpdate, session: SessionDep) -> PersonRead:
    return await service.update_person(session, person_id, data)


@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(404, 409))
async def delete_person(person_id: uuid.UUID, session: SessionDep) -> None:
    await service.delete_person(session, person_id)
