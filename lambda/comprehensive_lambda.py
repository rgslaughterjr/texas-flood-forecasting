cat > comprehensive_lambda.py << 'EOF'
import json
import urllib.request
import boto3
import math
from datetime import datetime, timezone

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
s3 = boto3.client('s3')

def lambda_handler(event, context):
    try:
        lat = float(event['queryStringParameters']['lat'])
        lon = float(event['queryStringParameters']['lon'])
        location = event['queryStringParameters']['location']
        forecast_hours = event['queryStringParameters'].get('forecastHours', '24')
        
        flood_data = fetch_comprehensive_data(lat, lon)
        forecast = generate_ai_forecast(flood_data, location, lat, lon, forecast_hours)
        
        return {
            'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps(forecast)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'risk_level': 'ERROR', 'error': str(e)})
        }

def get_texas_mesonet_data(lat, lon):
    try:
        current_data_url = "https://www.texmesonet.org/api/CurrentData"
        current_data_response = fetch_api_data(current_data_url, 'TexMesonet Current Data')
        
        if not current_data_response or 'data' not in current_data_response:
            return {'status': 'Unavailable'}
        
        current_data = current_data_response['data']
        station_data = []
        
        for data_point in current_data:
            try:
                if not (data_point.get('latitude') and data_point.get('longitude')):
                    continue
                    
                station_lat = float(data_point['latitude'])
                station_lon = float(data_point['longitude'])
                distance = math.sqrt((lat - station_lat)**2 + (lon - station_lon)**2) * 69
                
                if distance <= 50:
                    precip_mm = float(data_point.get('precip24Hr') or 0)
                    station_data.append({
                        'station_id': data_point.get('stationId'),
                        'station_name': data_point.get('name'),
                        'distance': round(distance, 1),
                        'temperature': float(data_point.get('airTemp') or 0),
                        'humidity': float(data_point.get('humidity') or 0),
                        'precipitation': round(precip_mm / 25.4, 2),
                        'soil_moisture': float(data_point.get('soilMoisture') or 0)
                    })
            except (ValueError, TypeError):
                continue
        
        if not station_data:
            return {'status': 'No nearby stations'}
        
        station_data.sort(key=lambda x: x['distance'])
        station_data = station_data[:5]
        
        temps = [s['temperature'] for s in station_data if s['temperature'] > 0]
        humidity = [s['humidity'] for s in station_data if s['humidity'] > 0]
        precip = [s['precipitation'] for s in station_data]
        soil = [s['soil_moisture'] for s in station_data if s['soil_moisture'] > 0]
        
        return {
            'status': 'Active',
            'stations_count': len(station_data),
            'regional_averages': {
                'temperature': round(sum(temps) / len(temps), 1) if temps else None,
                'humidity': round(sum(humidity) / len(humidity), 1) if humidity else None,
                'precipitation_24h': round(sum(precip), 2),
                'soil_saturation': round(sum(soil) / len(soil) * 100, 1) if soil else None
            },
            'stations': station_data
        }
        
    except Exception as e:
        return {'status': 'Error', 'error': str(e)}

def fetch_comprehensive_data(lat, lon):
    data = {'source_count': 0}
    
    usgs_url = f"https://waterservices.usgs.gov/nwis/iv/?format=json&parameterCd=00065,00060&bBox={lon-0.5},{lat-0.5},{lon+0.5},{lat+0.5}&siteStatus=active"
    data['usgs'] = fetch_api_data(usgs_url, 'USGS')
    if data['usgs']: data['source_count'] += 1
    
    data['texas_mesonet'] = get_texas_mesonet_data(lat, lon)
    if data['texas_mesonet'].get('status') == 'Active': 
        data['source_count'] += 1
    
    nws_point = f"https://api.weather.gov/points/{lat},{lon}"
    point_data = fetch_api_data(nws_point, 'NWS Point')
    if point_data:
        data['nws_forecast'] = fetch_api_data(point_data.get('properties', {}).get('forecast'), 'NWS Forecast')
        data['nws_hourly'] = fetch_api_data(point_data.get('properties', {}).get('forecastHourly'), 'NWS Hourly')
        data['nws_alerts'] = fetch_api_data(f"https://api.weather.gov/alerts/active?point={lat},{lon}", 'NWS Alerts')
        if data['nws_forecast'] or data['nws_hourly'] or data['nws_alerts']:
            data['source_count'] += 1
    
    data['lcra_flow'] = fetch_api_data('https://hydromet.lcra.org/api/GetStageFlowForAllSites', 'LCRA Flow')
    if data['lcra_flow']: data['source_count'] += 1
    
    data['lcra_lakes'] = fetch_api_data('https://hydromet.lcra.org/api/GetHighlandLakesSummary', 'LCRA Lakes')
    if data['lcra_lakes']: data['source_count'] += 1
    
    data['nexrad'] = get_nexrad_status(lat, lon)
    if data['nexrad'].get('status') == 'Active': data['source_count'] += 1
    
    return data

def fetch_api_data(url, source_name):
    if not url: return None
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'TexasFloodForecast/1.0')
        with urllib.request.urlopen(req, timeout=8) as response:
            result = json.loads(response.read())
            print(f"✓ {source_name}: Success")
            return result
    except Exception as e:
        print(f"✗ {source_name}: {str(e)}")
        return None

def get_nexrad_status(lat, lon):
    try:
        today = datetime.now().strftime('%Y/%m/%d')
        response = s3.list_objects_v2(
            Bucket='noaa-nexrad-level2',
            Prefix=f'{today}/KEWX/',
            MaxKeys=3
        )
        if response.get('Contents'):
            return {'status': 'Active', 'radar_site': 'KEWX'}
    except:
        pass
    return {'status': 'Unavailable'}

def generate_ai_forecast(flood_data, location, lat, lon, forecast_hours):
    try:
        mesonet_data = flood_data.get('texas_mesonet', {})
        mesonet_summary = ""
        if mesonet_data.get('status') == 'Active':
            avg = mesonet_data.get('regional_averages', {})
            mesonet_summary = f"""
TexMesonet Data ({mesonet_data.get('stations_count', 0)} stations):
- Regional temperature: {avg.get('temperature')}°F
- Regional humidity: {avg.get('humidity')}%
- 24h precipitation: {avg.get('precipitation_24h')} inches
- Soil saturation: {avg.get('soil_saturation')}%"""

        prompt = f"""Generate {forecast_hours}-hour flood forecast for {location} at {lat}, {lon}.

Data sources: {flood_data.get('source_count', 0)} active
USGS gauges: {len(flood_data.get('usgs', {}).get('value', {}).get('timeSeries', []))}
LCRA stations: {len(flood_data.get('lcra_flow', []))}
Weather alerts: {len(flood_data.get('nws_alerts', {}).get('features', []))}
{mesonet_summary}

Respond with JSON only:
{{
    "risk_level": "LOW|MODERATE|HIGH|CRITICAL",
    "risk_score": 0-100,
    "confidence": 0-100,
    "key_factors": ["factor1", "factor2"],
    "reasoning": "analysis specific to {forecast_hours}-hour period",
    "recommendations": ["action1", "action2"],
    "temporal_forecast": "{forecast_hours}-hour progression"
}}"""

        response = bedrock.invoke_model(
            modelId='anthropic.claude-3-haiku-20240307-v1:0',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 800,
                'messages': [{'role': 'user', 'content': prompt}]
            })
        )
        
        result = json.loads(response['body'].read())
        ai_response = json.loads(result['content'][0]['text'])
        
        ai_response.update({
            'location': location,
            'coordinates': [lat, lon],
            'generated_at': datetime.utcnow().isoformat(),
            'model': 'claude-3-haiku',
            'sources_analyzed': flood_data.get('source_count', 0),
            'forecast_period': f'{forecast_hours}_hours',
            'texas_mesonet_stations': mesonet_data.get('stations_count', 0)
        })
        
        return ai_response
        
    except Exception as e:
        return {
            'risk_level': 'ERROR',
            'error': str(e),
            'location': location,
            'coordinates': [lat, lon],
            'forecast_period': f'{forecast_hours}_hours'
        }
EOF

zip comprehensive_lambda.zip comprehensive_lambda.py
aws lambda update-function-code --function-name texas-flood-ai --zip-file fileb://comprehensive_lambda.zip
