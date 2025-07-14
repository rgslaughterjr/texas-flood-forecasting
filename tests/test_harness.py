#!/usr/bin/env python3
"""
Test harness to verify the AI generates unique, location-specific forecasts
"""

import requests
import json
import time
from datetime import datetime

API_URL = "https://2bv3vlwhx9.execute-api.us-east-1.amazonaws.com/prod/forecast"

# Test locations with different flood risk profiles
test_locations = [
    {"name": "West Austin (Urban)", "lat": 30.3074, "lon": -97.7415},
    {"name": "Rocksprings (Hill Country)", "lat": 29.9897, "lon": -100.2087},
    {"name": "Kickapoo Kamp (River)", "lat": 30.0, "lon": -98.0},
    {"name": "Hudson Bend (Lake)", "lat": 30.3928, "lon": -97.7639},
    {"name": "Panther Canyon (Remote)", "lat": 29.882378, "lon": -100.088261}
]

forecast_periods = ["12", "24", "48"]

def test_unique_forecasts():
    """Test that different locations produce different forecasts"""
    print("=== TESTING UNIQUE LOCATION-SPECIFIC FORECASTS ===\n")
    
    results = {}
    
    for period in forecast_periods:
        print(f"🕐 Testing {period}-hour forecasts:")
        period_results = []
        
        for loc in test_locations:
            params = {
                "lat": loc["lat"],
                "lon": loc["lon"], 
                "location": loc["name"],
                "forecastHours": period
            }
            
            try:
                response = requests.get(API_URL, params=params, timeout=30)
                data = response.json()
                
                if response.status_code == 200 and data.get('risk_level') != 'ERROR':
                    period_results.append({
                        'location': loc['name'],
                        'risk_level': data.get('risk_level'),
                        'risk_score': data.get('risk_score', 0),
                        'reasoning_length': len(data.get('reasoning', '')),
                        'key_factors': len(data.get('key_factors', [])),
                        'sources_analyzed': data.get('sources_analyzed', 0),
                        'forecast_period': data.get('forecast_period', 'unknown')
                    })
                    print(f"  ✅ {loc['name']}: {data.get('risk_level')} ({data.get('risk_score', 0)}/100)")
                else:
                    print(f"  ❌ {loc['name']}: ERROR - {data.get('error', 'Unknown error')}")
                    
            except Exception as e:
                print(f"  ❌ {loc['name']}: FAILED - {str(e)}")
            
            time.sleep(2)  # Rate limiting
        
        results[period] = period_results
        print()
    
    return results

def analyze_uniqueness(results):
    """Analyze if forecasts are truly unique and location-specific"""
    print("=== UNIQUENESS ANALYSIS ===\n")
    
    for period, period_results in results.items():
        if not period_results:
            continue
            
        print(f"📊 {period}-hour Forecast Analysis:")
        
        # Check risk level diversity
        risk_levels = [r['risk_level'] for r in period_results]
        unique_risks = set(risk_levels)
        print(f"  Risk Level Diversity: {len(unique_risks)}/{len(period_results)} unique levels")
        
        # Check risk score variance
        risk_scores = [r['risk_score'] for r in period_results]
        if len(set(risk_scores)) > 1:
            variance = sum((x - sum(risk_scores)/len(risk_scores))**2 for x in risk_scores) / len(risk_scores)
            print(f"  Risk Score Variance: {variance:.1f} (higher = more diverse)")
        
        # Check reasoning uniqueness
        reasoning_lengths = [r['reasoning_length'] for r in period_results]
        avg_reasoning = sum(reasoning_lengths) / len(reasoning_lengths)
        print(f"  Average Reasoning Length: {avg_reasoning:.0f} characters")
        
        # Check data source utilization
        sources = [r['sources_analyzed'] for r in period_results]
        avg_sources = sum(sources) / len(sources)
        print(f"  Average Data Sources: {avg_sources:.1f}")
        
        # Forecast period verification
        periods_correct = sum(1 for r in period_results if period in str(r['forecast_period']))
        print(f"  Forecast Period Accuracy: {periods_correct}/{len(period_results)} correct")
        
        print()

def test_temporal_specificity():
    """Test that different forecast periods produce different temporal details"""
    print("=== TEMPORAL SPECIFICITY TEST ===\n")
    
    test_location = test_locations[0]  # Use West Austin
    
    temporal_results = []
    
    for period in forecast_periods:
        params = {
            "lat": test_location["lat"],
            "lon": test_location["lon"],
            "location": test_location["name"],
            "forecastHours": period
        }
        
        try:
            response = requests.get(API_URL, params=params, timeout=30)
            data = response.json()
            
            if response.status_code == 200:
                temporal_results.append({
                    'period': period,
                    'temporal_forecast': data.get('temporal_forecast', ''),
                    'reasoning': data.get('reasoning', ''),
                    'mentions_period': period in data.get('reasoning', '') + data.get('temporal_forecast', '')
                })
                
                print(f"🕐 {period}-hour forecast:")
                print(f"  Period mentioned in text: {'✅' if temporal_results[-1]['mentions_period'] else '❌'}")
                print(f"  Reasoning length: {len(data.get('reasoning', ''))} chars")
                if data.get('temporal_forecast'):
                    print(f"  Temporal details: {len(data.get('temporal_forecast', ''))} chars")
                print()
                
        except Exception as e:
            print(f"❌ {period}-hour test failed: {str(e)}\n")
        
        time.sleep(2)
    
    return temporal_results

def main():
    """Run complete test suite"""
    print("🚀 TEXAS FLOOD AI VERIFICATION TEST SUITE")
    print("=" * 50)
    print(f"Test started: {datetime.now()}\n")
    
    # Test 1: Unique location forecasts
    forecast_results = test_unique_forecasts()
    
    # Test 2: Analyze uniqueness
    analyze_uniqueness(forecast_results)
    
    # Test 3: Temporal specificity  
    temporal_results = test_temporal_specificity()
    
    # Final assessment
    print("=== FINAL ASSESSMENT ===\n")
    
    total_tests = sum(len(results) for results in forecast_results.values())
    successful_tests = sum(len([r for r in results if r]) for results in forecast_results.values())
    
    print(f"✅ Successful API calls: {successful_tests}/{total_tests}")
    
    if successful_tests > 0:
        all_risks = []
        all_scores = []
        for results in forecast_results.values():
            for r in results:
                all_risks.append(r['risk_level'])
                all_scores.append(r['risk_score'])
        
        unique_risk_levels = len(set(all_risks))
        unique_risk_scores = len(set(all_scores))
        
        print(f"🎯 Risk Level Diversity: {unique_risk_levels} unique levels")
        print(f"📊 Risk Score Diversity: {unique_risk_scores} unique scores")
        print(f"⏱️ Temporal Accuracy: {sum(1 for t in temporal_results if t['mentions_period'])}/{len(temporal_results)} periods referenced")
        
        if unique_risk_levels >= 2 and unique_risk_scores >= 3:
            print("\n🎉 SUCCESS: AI generates unique, location-specific forecasts!")
        else:
            print("\n⚠️  WARNING: Limited forecast diversity detected")
    else:
        print("\n❌ FAILED: Unable to generate forecasts")
    
    print(f"\nTest completed: {datetime.now()}")

if __name__ == "__main__":
    main()
