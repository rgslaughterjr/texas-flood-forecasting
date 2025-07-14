# Texas AI Flood Forecasting System

Real-time flood risk assessment powered by Claude 3 Haiku and AWS.

## Live Demo
- **Web App**: http://texas-flood-forecast-hc0881.s3-website-us-east-1.amazonaws.com
- **API**: https://2bv3vlwhx9.execute-api.us-east-1.amazonaws.com/prod/forecast

## Architecture
Frontend (S3) → API Gateway → Lambda (Bedrock AI) → External APIs

## Data Sources
- USGS Stream Gauges (159 active)
- National Weather Service
- NEXRAD Radar
- LCRA Hydromet

## Features
- 12/24/48/72 hour forecasts
- AI-powered risk assessment
- Real-time data integration
- Geographic flood analysis

## Quick Deploy
1. Deploy Lambda: `aws lambda update-function-code --function-name texas-flood-ai --zip-file fileb://lambda.zip`
2. Upload frontend: `aws s3 cp frontend/index.html s3://your-bucket/`
3. Test: `python3 tests/test_harness.py`

## Cost: ~$10-20/month
