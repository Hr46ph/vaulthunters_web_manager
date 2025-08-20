import psutil
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional


class TemperatureMonitor:
    """Service for monitoring hardware temperature sensors"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._last_reading = {}
        self._reading_cache = {}
        self._cache_duration = 2  # Cache for 2 seconds to avoid excessive sensor reads
        
    def get_temperature_readings(self) -> Dict:
        """Get current temperature readings from all available sensors"""
        current_time = time.time()
        
        # Check cache first
        if self._reading_cache and current_time - self._reading_cache.get('timestamp', 0) < self._cache_duration:
            return self._reading_cache.get('data', {})
        
        try:
            temperatures = {
                'cpu': None,
                'nvme': {'composite': None, 'sensor1': None},
                'gpu': None,
                'timestamp': datetime.now().isoformat(),
                'status': 'success'
            }
            
            # Get all available temperature sensors
            sensor_data = psutil.sensors_temperatures()
            
            # Process k10temp (AMD CPU)
            if 'k10temp' in sensor_data:
                for sensor in sensor_data['k10temp']:
                    if sensor.label == 'Tctl':
                        temperatures['cpu'] = {
                            'current': round(sensor.current, 1),
                            'high': sensor.high,
                            'critical': sensor.critical,
                            'sensor': 'k10temp-pci-00c3',
                            'label': 'Tctl'
                        }
                        break
            
            # Process NVMe SSD temperatures
            if 'nvme' in sensor_data:
                for sensor in sensor_data['nvme']:
                    if sensor.label == 'Composite':
                        temperatures['nvme']['composite'] = {
                            'current': round(sensor.current, 1),
                            'high': sensor.high if sensor.high and sensor.high < 1000 else None,
                            'critical': sensor.critical if sensor.critical and sensor.critical < 1000 else None,
                            'sensor': 'nvme-pci-0400',
                            'label': 'Composite'
                        }
                    elif sensor.label == 'Sensor 1':
                        temperatures['nvme']['sensor1'] = {
                            'current': round(sensor.current, 1),
                            'high': sensor.high if sensor.high and sensor.high < 1000 else None,
                            'critical': sensor.critical if sensor.critical and sensor.critical < 1000 else None,
                            'sensor': 'nvme-pci-0400',
                            'label': 'Sensor 1'
                        }
            
            # Process AMD GPU (amdgpu)
            if 'amdgpu' in sensor_data:
                for sensor in sensor_data['amdgpu']:
                    if sensor.label == 'edge':
                        temperatures['gpu'] = {
                            'current': round(sensor.current, 1),
                            'high': sensor.high,
                            'critical': sensor.critical,
                            'sensor': 'amdgpu-pci-0500',
                            'label': 'edge'
                        }
                        break
            
            # Cache the result
            self._reading_cache = {
                'data': temperatures,
                'timestamp': current_time
            }
            
            self.logger.debug(f"Temperature readings: CPU={temperatures['cpu']['current'] if temperatures['cpu'] else 'N/A'}°C, "
                            f"GPU={temperatures['gpu']['current'] if temperatures['gpu'] else 'N/A'}°C, "
                            f"NVMe={temperatures['nvme']['composite']['current'] if temperatures['nvme']['composite'] else 'N/A'}°C")
            
            return temperatures
            
        except Exception as e:
            self.logger.error(f"Error reading temperature sensors: {e}")
            return {
                'cpu': None,
                'nvme': {'composite': None, 'sensor1': None},
                'gpu': None,
                'timestamp': datetime.now().isoformat(),
                'status': 'error',
                'error': str(e)
            }
    
    def get_temperature_summary(self) -> Dict:
        """Get a simplified temperature summary for dashboard display"""
        readings = self.get_temperature_readings()
        
        summary = {
            'temperatures': {},
            'alerts': [],
            'timestamp': readings.get('timestamp'),
            'status': readings.get('status', 'unknown')
        }
        
        # CPU temperature
        if readings.get('cpu'):
            cpu_temp = readings['cpu']['current']
            summary['temperatures']['cpu'] = cpu_temp
            
            # Check for high temperatures (AMD typically throttles around 90°C)
            if cpu_temp >= 85:
                summary['alerts'].append({'type': 'critical', 'component': 'CPU', 'temp': cpu_temp, 'message': 'CPU temperature critical'})
            elif cpu_temp >= 75:
                summary['alerts'].append({'type': 'warning', 'component': 'CPU', 'temp': cpu_temp, 'message': 'CPU temperature high'})
        
        # GPU temperature
        if readings.get('gpu'):
            gpu_temp = readings['gpu']['current']
            summary['temperatures']['gpu'] = gpu_temp
            
            # Check for high temperatures (AMD GPUs typically throttle around 90-100°C)
            if gpu_temp >= 90:
                summary['alerts'].append({'type': 'critical', 'component': 'GPU', 'temp': gpu_temp, 'message': 'GPU temperature critical'})
            elif gpu_temp >= 80:
                summary['alerts'].append({'type': 'warning', 'component': 'GPU', 'temp': gpu_temp, 'message': 'GPU temperature high'})
        
        # NVMe temperature (using composite reading)
        if readings.get('nvme', {}).get('composite'):
            nvme_temp = readings['nvme']['composite']['current']
            summary['temperatures']['nvme'] = nvme_temp
            
            # Check for high temperatures (NVMe SSDs typically throttle around 70-80°C)
            if nvme_temp >= 70:
                summary['alerts'].append({'type': 'critical', 'component': 'NVMe SSD', 'temp': nvme_temp, 'message': 'NVMe temperature critical'})
            elif nvme_temp >= 60:
                summary['alerts'].append({'type': 'warning', 'component': 'NVMe SSD', 'temp': nvme_temp, 'message': 'NVMe temperature high'})
        
        return summary
    
    def get_available_sensors(self) -> List[Dict]:
        """Get list of all available temperature sensors"""
        try:
            sensors = []
            sensor_data = psutil.sensors_temperatures()
            
            for sensor_type, sensor_list in sensor_data.items():
                for sensor in sensor_list:
                    sensors.append({
                        'type': sensor_type,
                        'label': sensor.label,
                        'current': sensor.current,
                        'high': sensor.high,
                        'critical': sensor.critical
                    })
            
            return sensors
            
        except Exception as e:
            self.logger.error(f"Error getting available sensors: {e}")
            return []


# Global instance for easy access
_temperature_monitor = None

def get_temperature_monitor() -> TemperatureMonitor:
    """Get the global temperature monitor instance"""
    global _temperature_monitor
    if _temperature_monitor is None:
        _temperature_monitor = TemperatureMonitor()
    return _temperature_monitor