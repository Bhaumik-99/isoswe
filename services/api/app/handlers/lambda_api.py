"""AWS Lambda API Gateway Handler

Uses Mangum adapter to execute the FastAPI application within an AWS Lambda environment.
"""

from mangum import Mangum

from app.main import app

# Mangum handler with lifespan off for optimized cold start in serverless execution
handler = Mangum(app, lifespan="off")
