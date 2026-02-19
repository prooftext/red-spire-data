from fastapi import APIRouter, HTTPException
from app.database import get_pool

router = APIRouter()

@router.get("/detector-performance")
async def detector_performance():
    pool = get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database connection not initialized")

    async with pool.connection() as conn:
        per_detector_cursor = await conn.execute(
            """
            SELECT
                detector_name,
                COUNT(*) AS total,
                AVG(detector_score) AS avg_score,
                SUM(CASE WHEN detector_label = 'AI' THEN 1 ELSE 0 END) AS ai_count,
                SUM(CASE WHEN detector_label = 'HUMAN' THEN 1 ELSE 0 END) AS human_count
            FROM ai_detector_comparisons
            GROUP BY detector_name
            ORDER BY detector_name
            """
        )
        per_detector_rows = await per_detector_cursor.fetchall()

        daily_cursor = await conn.execute(
            """
            SELECT
                date_trunc('day', created_at) AS day,
                detector_name,
                COUNT(*) AS total,
                AVG(detector_score) AS avg_score,
                AVG(CASE WHEN detector_label = 'AI' THEN 1 ELSE 0 END) AS ai_rate
            FROM ai_detector_comparisons
            WHERE created_at >= NOW() - INTERVAL '30 days'
            GROUP BY day, detector_name
            ORDER BY day ASC, detector_name ASC
            """
        )
        daily_rows = await daily_cursor.fetchall()

    per_detector = []
    for row in per_detector_rows:
        per_detector.append({
            "detector": row[0],
            "total": row[1],
            "avg_score": float(row[2]) if row[2] is not None else None,
            "ai_count": row[3],
            "human_count": row[4],
        })

    daily = []
    for row in daily_rows:
        daily.append({
            "day": row[0].date().isoformat() if row[0] else None,
            "detector": row[1],
            "total": row[2],
            "avg_score": float(row[3]) if row[3] is not None else None,
            "ai_rate": float(row[4]) if row[4] is not None else None,
        })

    return {
        "per_detector": per_detector,
        "daily": daily,
    }
