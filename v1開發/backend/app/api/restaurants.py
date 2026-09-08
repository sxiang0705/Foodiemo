from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy.orm import Session
from app.repositories.restaurants import RestaurantRepository
from app.schemas.restaurants import RestaurantDetail, RestaurantPage, ReviewPage

router = APIRouter(prefix="/api/v1/restaurants", tags=["restaurants"])


def get_repository(request: Request):
    with Session(request.app.state.engine) as session:
        yield RestaurantRepository(session)


@router.get("", response_model=RestaurantPage)
def restaurants(page: int = Query(1, ge=1, le=10000), page_size: int = Query(12, ge=1, le=50),
                q: str = Query("", max_length=100), category: str = Query("", max_length=100),
                repo=Depends(get_repository)):
    return repo.list(page, page_size, q.strip(), category.strip())


@router.get("/{restaurant_id}", response_model=RestaurantDetail)
def detail(restaurant_id: int = Path(ge=1, le=9223372036854775807), repo=Depends(get_repository)):
    result = repo.detail(restaurant_id)
    if result is None:
        raise HTTPException(404, "RESTAURANT_NOT_FOUND")
    return result


@router.get("/{restaurant_id}/reviews", response_model=ReviewPage)
def reviews(restaurant_id: int = Path(ge=1, le=9223372036854775807),
            page: int = Query(1, ge=1, le=10000), page_size: int = Query(10, ge=1, le=50),
            repo=Depends(get_repository)):
    result = repo.reviews(restaurant_id, page, page_size)
    if result is None:
        raise HTTPException(404, "RESTAURANT_NOT_FOUND")
    return result
