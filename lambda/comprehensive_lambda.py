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
    """Get Texas Mesonet weather data using CurrentData directly"""
    try:
        # Get current data (includes station info)
        current_data_url = "https://www.texmesonet.org/api/CurrentData"
        current_data_response = fetch_api_data(current_data_url, 'TexMesonet Current Data')
        
        if not current_data_response:
            return {'status': 'Unavailable', 'error': 'Could not fetch current data'}
        
        current_data = current_data_response.get('data', [])
        
        # Find nearby stations with data (within 50 miles)
        station_data = []
        for data_point in current_data:
            if 'latitude' in data_point and 'longitude' in data_point:
                station_lat = float(data_point['latitude'])
                station_lon = float(data_point['longitude'])
                distance = math.sqrt((lat - station_lat)**2 + (lon - station_lon)**2) * 69
                
                if distance <= 50:
                    station_data.append({
                        'station_id': data_point.get('stationId'),
                        'station_name': data_point.get('name'),
                        'distance': round(distance, 1),
                        'temperature': data_point.get('airTemp'),
                        'humidity': data_point.get('humidity'),
                        'precipitation': data_point.get('precip24Hr'),
                        'soil_moisture': data_point.get('soilMoisture')
                    })
        
        station_data.sort(key=lambda x: x['distance'])
        station_data = station_data[:5]
        
        if not station_data:
            return {'status': 'No nearby stations'}
        
        # Calculate regional averages
        temps = [float(s['temperature']) for s in station_data if s['temperature'] is not None]
        humidity = [float(s['humidity']) for s in station_data if s['humidity'] is not None]
        precip = [float(s['precipitation']) for s in station_data if s['precipitation'] is not None]
        soil_moisture = [float(s['soil_moisture']) for s in station_data if s['soil_moisture'] is not None]
        
        return {
            'status': 'Active',
            'stations_count': len(station_data),
            'regional_averages': {
                'temperature': round(sum(temps) / len(temps), 1) if temps else None,
                'humidity': round(sum(humidity) / len(humidity), 1) if humidity else None,
                'precipitation_24h': round(sum(precip), 2) if precip else 0.0,
                'soil_saturation': round(sum(soil_moisture) / len(soil_moisture), 1) if soil_moisture else None
            },
            'stations': station_data
        }
        
    except Exception as e:
        return {'status': 'Error', 'error': str(e)}

def fetch_comprehensive_data(lat, lon):
    data = {'source_count': 0}
    
    # USGS Stream Gauges
    usgs_url = f"https://waterservices.usgs.gov/nwis/iv/?format=json&parameterCd=00065,00060&bBox={lon-0.5},{lat-0.5},{lon+0.5},{lat+0.5}&siteStatus=active"
    data['usgs'] = fetch_api_data(usgs_url, 'USGS')
    if data['usgs']: data['source_count'] += 1
    
    # Texas Mesonet
    data['texas_mesonet'] = get_texas_mesonet_data(lat, lon)
    if data['texas_mesonet'].get('status') == 'Active': 
        data['source_count'] += 1
    
    # NWS Weather
    nws_point = f"https://api.weather.gov/points/{lat},{lon}"
    point_data = fetch_api_data(nws_point, 'NWS Point')
    if point_data:
        data['nws_forecast'] = fetch_api_data(point_data.get('properties', {}).get('forecast'), 'NWS Forecast')
        data['nws_hourly'] = fetch_api_data(point_data.get('properties', {}).get('forecastHourly'), 'NWS Hourly')
        data['nws_alerts'] = fetch_api_data(f"https://api.weather.gov/alerts/active?point={lat},{lon}", 'NWS Alerts')
        if data['nws_forecast'] or data['nws_hourly'] or data['nws_alerts']:
            data['source_count'] += 1
    
    # LCRA Flow Data
    data['lcra_flow'] = fetch_api_data('https://hydromet.lcra.org/api/GetStageFlowForAllSites', 'LCRA Flow')
    if data['lcra_flow']: data['source_count'] += 1
    
    # LCRA Lake Levels
    data['lcra_lakes'] = fetch_api_data('https://hydromet.lcra.org/api/GetHighlandLakesSummary', 'LCRA Lakes')
    if data['lcra_lakes']: data['source_count'] += 1
    
    # NEXRAD Radar Status
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
        # Enhanced prompt with TexMesonet data
        mesonet_data = flood_data.get('texas_mesonet', {})
        mesonet_summary = ""
        if mesonet_data.get('status') == 'Active':
            avg = mesonet_data.get('regional_averages', {})
            indicators = mesonet_data.get('flood_indicators', {})
            mesonet_summary = f"""
TexMesonet Data ({mesonet_data.get('stations_count', 0)} stations):
- Regional temperature: {avg.get('temperature')}°F
- Regional humidity: {avg.get('humidity')}%
- 24h precipitation: {avg.get('precipitation_24h')} inches
- Soil saturation: {avg.get('soil_saturation')}%
- High precip stations: {indicators.get('high_precip_stations', 0)}
- Saturated soil stations: {indicators.get('saturated_soil_stations', 0)}"""

        prompt = f"""Generate {forecast_hours}-hour flood forecast for {location} at {lat}, {lon}.

Data sources: {flood_data.get('source_count', 0)} active
USGS gauges: {len(flood_data.get('usgs', {}).get('value', {}).get('timeSeries', []))}
LCRA stations: {len(flood_data.get('lcra_flow', []))}
Weather alerts: {len(flood_data.get('nws_alerts', {}).get('features', []))}
{mesonet_summary}

Analyze specifically for the next {forecast_hours} hours. Consider:
- Stream gauge trends and capacity
- Weather forecast precipitation timing
- Soil saturation levels from TexMesonet
- Geographic flood risk factors

Respond with JSON only:
{{
    "risk_level": "LOW|MODERATE|HIGH|CRITICAL",
    "risk_score": 0-100,
    "confidence": 0-100,
    "key_factors": ["factor1", "factor2"],
    "reasoning": "analysis specific to {forecast_hours}-hour period including soil conditions",
    "recommendations": ["action1", "action2"],
    "temporal_forecast": "{forecast_hours}-hour progression details"
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
