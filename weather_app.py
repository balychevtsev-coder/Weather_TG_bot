import requests
from dotenv import load_dotenv
import os
from typing import Dict, List, Tuple, Optional
from colorama import init, Fore, Style

init(autoreset=True)

load_dotenv()
API_KEY = os.getenv("API_KEY")

def get_current_weather(city: str=None, latitude: float=None, longitude: float=None) -> dict:
    if city:
        print(f"Getting weather for {city}")
        latitude, longitude = get_coordinates(city)
        weather = get_weather_by_coordinates(latitude, longitude)
        return weather

    elif latitude and  longitude:
        print(f"Getting weather for latitude {latitude} and longitude {longitude}")
        return get_weather_by_coordinates(latitude, longitude)

def get_coordinates(city: str) -> tuple:
    url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&appid={API_KEY}"
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to get coordinates for {city}")
        return None
    return response.json()[0]["lat"], response.json()[0]["lon"]

def get_weather_by_coordinates(latitude: float, longitude: float) -> dict:
    url=f"https://api.openweathermap.org/data/2.5/weather?lat={latitude}&lon={longitude}&appid={API_KEY}&units=metric"
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to get weather for latitude {latitude} and longitude {longitude}")
        return None
    return response.json()

def get_hourly_weather(latitude: float, longitude: float) -> dict:
    """Получает прогноз погоды на 5 дней вперед"""
    url=f"https://api.openweathermap.org/data/2.5/forecast?lat={latitude}&lon={longitude}&appid={API_KEY}&units=metric"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"Failed to get hourly weather: status_code={response.status_code}, response={response.text[:200]}")
            return None
        data = response.json()
        print(f"DEBUG weather_app: Получен прогноз, элементов в списке: {len(data.get('list', []))}")
        return data
    except Exception as e:
        print(f"Error in get_hourly_weather: {e}")
        import traceback
        print(traceback.format_exc())
        return None

def get_air_pollution(latitude: float, longitude: float) -> dict:
    url=f"https://api.openweathermap.org/data/2.5/air_pollution?lat={latitude}&lon={longitude}&appid={API_KEY}&units=metric"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"Failed to get air pollution: status_code={response.status_code}, response={response.text[:200]}")
            return None
        return response.json()
    except Exception as e:
        print(f"Error in get_air_pollution: {e}")
        import traceback
        print(traceback.format_exc())
        return None 

# Таблица качества воздуха согласно стандартам
AIR_QUALITY_STANDARDS = {
    1: {
        "name": "Good",
        "ranges": {
            "SO₂": (0, 20),
            "NO₂": (0, 40),
            "PM₁₀": (0, 20),
            "PM₂.₅": (0, 10),
            "O₃": (0, 60),
            "CO": (0, 4400)
        }
    },
    2: {
        "name": "Fair",
        "ranges": {
            "SO₂": (20, 80),
            "NO₂": (40, 70),
            "PM₁₀": (20, 50),
            "PM₂.₅": (10, 25),
            "O₃": (60, 100),
            "CO": (4400, 9400)
        }
    },
    3: {
        "name": "Moderate",
        "ranges": {
            "SO₂": (80, 250),
            "NO₂": (70, 150),
            "PM₁₀": (50, 100),
            "PM₂.₅": (25, 50),
            "O₃": (100, 140),
            "CO": (9400, 12400)
        }
    },
    4: {
        "name": "Poor",
        "ranges": {
            "SO₂": (250, 350),
            "NO₂": (150, 200),
            "PM₁₀": (100, 200),
            "PM₂.₅": (50, 75),
            "O₃": (140, 180),
            "CO": (12400, 15400)
        }
    },
    5: {
        "name": "Very Poor",
        "ranges": {
            "SO₂": (350, float('inf')),
            "NO₂": (200, float('inf')),
            "PM₁₀": (200, float('inf')),
            "PM₂.₅": (75, float('inf')),
            "O₃": (180, float('inf')),
            "CO": (15400, float('inf'))
        }
    }
}

# Маппинг названий загрязнителей из API к названиям в таблице
POLLUTANT_MAPPING = {
    "so2": "SO₂",
    "no2": "NO₂",
    "pm10": "PM₁₀",
    "pm2_5": "PM₂.₅",
    "o3": "O₃",
    "co": "CO"
}

def get_air_quality_index(pollutant: str, concentration: float) -> int:
    """Определяет индекс качества воздуха для конкретного загрязнителя"""
    pollutant_name = POLLUTANT_MAPPING.get(pollutant.lower(), pollutant.upper())
    
    for index in range(5, 0, -1):  # Проверяем от худшего к лучшему
        standard = AIR_QUALITY_STANDARDS[index]
        if pollutant_name in standard["ranges"]:
            min_val, max_val = standard["ranges"][pollutant_name]
            if min_val <= concentration < max_val:
                return index
            elif max_val == float('inf') and concentration >= min_val:
                return index
    
    # Если значение меньше минимального для индекса 1, возвращаем 1
    return 1

def analyze_air_pollution(air_pollution: dict) -> Dict:
    """Анализирует данные о загрязнении воздуха и выводит общий статус и детальную информацию"""
    
    if not air_pollution or "list" not in air_pollution or not air_pollution["list"]:
        return {"error": "Нет данных о загрязнении воздуха"}
    
    # Берем первые данные (текущее состояние)
    current_data = air_pollution["list"][0]
    components = current_data.get("components", {})
    
    # Конвертируем концентрации в мкг/м³ (API возвращает в мкг/м³, но CO может быть в мг/м³)
    pollutants = {
        "so2": components.get("so2", 0),      # µg/m³
        "no2": components.get("no2", 0),      # µg/m³
        "pm10": components.get("pm10", 0),    # µg/m³
        "pm2_5": components.get("pm2_5", 0),  # µg/m³
        "o3": components.get("o3", 0),        # µg/m³
        "co": components.get("co", 0) * 1000  # Конвертируем из мг/м³ в µg/m³
    }
    
    # Определяем индекс для каждого загрязнителя
    pollutant_indices = {}
    for pollutant, concentration in pollutants.items():
        pollutant_indices[pollutant] = get_air_quality_index(pollutant, concentration)
    
    # Общий статус - берем худший индекс
    overall_index = max(pollutant_indices.values())
    overall_status = AIR_QUALITY_STANDARDS[overall_index]["name"]
    
    # Определяем, что в норме и что превышает норму
    good_pollutants = []  # Индекс 1 (Good)
    fair_pollutants = []  # Индекс 2 (Fair)
    moderate_pollutants = []  # Индекс 3 (Moderate)
    poor_pollutants = []  # Индекс 4 (Poor)
    very_poor_pollutants = []  # Индекс 5 (Very Poor)
    
    for pollutant, index in pollutant_indices.items():
        pollutant_name = POLLUTANT_MAPPING.get(pollutant.lower(), pollutant.upper())
        concentration = pollutants[pollutant]
        
        info = {
            "name": pollutant_name,
            "concentration": concentration,
            "index": index,
            "status": AIR_QUALITY_STANDARDS[index]["name"]
        }
        
        if index == 1:
            good_pollutants.append(info)
        elif index == 2:
            fair_pollutants.append(info)
        elif index == 3:
            moderate_pollutants.append(info)
        elif index == 4:
            poor_pollutants.append(info)
        elif index == 5:
            very_poor_pollutants.append(info)
    
    # Формируем результат
    result = {
        "overall_index": overall_index,
        "overall_status": overall_status,
        "pollutants": {
            "good": good_pollutants,
            "fair": fair_pollutants,
            "moderate": moderate_pollutants,
            "poor": poor_pollutants,
            "very_poor": very_poor_pollutants
        },
        "pollutant_indices": pollutant_indices,
        "pollutants_data": pollutants
    }
    
    return result

def print_air_pollution_analysis(analysis_result: Dict) -> None:
    """Выводит красивый анализ качества воздуха"""
    
    if "error" in analysis_result:
        print(f"{Fore.RED}{analysis_result['error']}{Style.RESET_ALL}")
        return
    
    overall_index = analysis_result["overall_index"]
    overall_status = analysis_result["overall_status"]
    pollutants = analysis_result["pollutants"]
    
    # Цвета для разных статусов
    status_colors = {
        1: Fore.GREEN,
        2: Fore.CYAN,
        3: Fore.YELLOW,
        4: Fore.MAGENTA,
        5: Fore.RED
    }
    
    color = status_colors.get(overall_index, Fore.WHITE)
    
    # Выводим общий статус
    print(f"\n{Fore.GREEN}{'='*70}")
    print(f"{'='*20} АНАЛИЗ КАЧЕСТВА ВОЗДУХА {'='*20}")
    print(f"{'='*70}{Style.RESET_ALL}\n")
    
    print(f"{color}Общий статус: {overall_status} (Индекс: {overall_index}){Style.RESET_ALL}\n")
    
    # Выводим детальную информацию по категориям
    if pollutants["very_poor"]:
        print(f"{Fore.RED}⚠️  ОЧЕНЬ ПЛОХОЕ качество:{Style.RESET_ALL}")
        for p in pollutants["very_poor"]:
            print(f"   {Fore.RED}• {p['name']}: {p['concentration']:.2f} µg/m³ (Индекс: {p['index']}){Style.RESET_ALL}")
        print()
    
    if pollutants["poor"]:
        print(f"{Fore.MAGENTA}⚠️  ПЛОХОЕ качество:{Style.RESET_ALL}")
        for p in pollutants["poor"]:
            print(f"   {Fore.MAGENTA}• {p['name']}: {p['concentration']:.2f} µg/m³ (Индекс: {p['index']}){Style.RESET_ALL}")
        print()
    
    if pollutants["moderate"]:
        print(f"{Fore.YELLOW}⚠️  УМЕРЕННОЕ качество:{Style.RESET_ALL}")
        for p in pollutants["moderate"]:
            print(f"   {Fore.YELLOW}• {p['name']}: {p['concentration']:.2f} µg/m³ (Индекс: {p['index']}){Style.RESET_ALL}")
        print()
    
    if pollutants["fair"]:
        print(f"{Fore.CYAN}✓  ХОРОШЕЕ качество:{Style.RESET_ALL}")
        for p in pollutants["fair"]:
            print(f"   {Fore.CYAN}• {p['name']}: {p['concentration']:.2f} µg/m³ (Индекс: {p['index']}){Style.RESET_ALL}")
        print()
    
    if pollutants["good"]:
        print(f"{Fore.GREEN}✓  ОТЛИЧНОЕ качество:{Style.RESET_ALL}")
        for p in pollutants["good"]:
            print(f"   {Fore.GREEN}• {p['name']}: {p['concentration']:.2f} µg/m³ (Индекс: {p['index']}){Style.RESET_ALL}")
        print()
    
    # Сводная таблица
    print(f"{Fore.CYAN}{'─'*70}")
    print(f"{'Загрязнитель':<15} {'Концентрация (µg/m³)':<25} {'Индекс':<10} {'Статус'}")
    print(f"{'─'*70}{Style.RESET_ALL}")
    
    all_pollutants = (
        pollutants["very_poor"] + pollutants["poor"] + pollutants["moderate"] + 
        pollutants["fair"] + pollutants["good"]
    )
    
    # Сортируем по индексу (от худшего к лучшему)
    all_pollutants.sort(key=lambda x: x["index"], reverse=True)
    
    for p in all_pollutants:
        color = status_colors.get(p["index"], Fore.WHITE)
        print(f"{color}{p['name']:<15} {p['concentration']:<25.2f} {p['index']:<10} {p['status']}{Style.RESET_ALL}")
    
    print(f"{Fore.CYAN}{'─'*70}{Style.RESET_ALL}\n")

if __name__ == "__main__":
#    city=input("Введите город: ")
#    weather = get_hourly_weather(get_coordinates(city))
#    print(f"Погода в {weather['name']}: {weather['main']['temp']}°C, {weather['weather'][0]['description']}")
    # Пример использования
    air_pollution_data = get_air_pollution(55.7558, 37.6173)
    if air_pollution_data:
        analysis = analyze_air_pollution(air_pollution_data)
        print_air_pollution_analysis(analysis)