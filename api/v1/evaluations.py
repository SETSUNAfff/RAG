from fastapi import APIRouter, HTTPException, status

# 评测接口占位，后续接入离线评测集和评测报告。
router = APIRouter(prefix="/evaluations")


@router.post("/runs", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def run_evaluations() -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Evaluation endpoint is not implemented yet",
    )


@router.get("/runs/{run_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def read_evaluation_run(run_id: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Evaluation endpoint is not implemented yet",
    )


@router.get("/cases", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_evaluation_cases() -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Evaluation endpoint is not implemented yet",
    )
